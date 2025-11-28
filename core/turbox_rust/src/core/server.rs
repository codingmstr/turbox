use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer, Responder, http::KeepAlive};
use pyo3::prelude::*;
use pyo3::ffi;
use pyo3::types::{PyString, PyBool, PyBytes, PyDict, PyModule};
use std::ptr;
use std::cell::RefCell;
use std::ffi::CString;
use std::collections::HashMap;
use pythonize::depythonize;
use serde_json::Value;
use bytes::Bytes;

use crate::core::route::{ROUTES, RouteKey};

thread_local! {
    static WORKER_INTERPRETER_STATE: RefCell<*mut ffi::PyThreadState> = RefCell::new(ptr::null_mut());
    static FUNCTION_CACHE: RefCell<HashMap<RouteKey, Py<PyAny>>> = RefCell::new(HashMap::new());
}

fn process_body(obj: &Bound<'_, PyAny>) -> Bytes {
    if let Ok(b) = obj.cast::<PyBytes>() {
        return Bytes::copy_from_slice(b.as_bytes());
    }
    if let Ok(s) = obj.cast::<PyString>() {
        return Bytes::copy_from_slice(s.to_string_lossy().as_bytes());
    }
    if let Ok(b) = obj.cast::<PyBool>() {
        return if b.is_true() { Bytes::from_static(b"true") } else { Bytes::from_static(b"false") };
    }
    match depythonize::<Value>(obj) {
        Ok(v) => Bytes::from(serde_json::to_vec(&v).unwrap_or_default()),
        Err(_) => {
            let s = obj.str().unwrap_or_else(|_| obj.repr().unwrap());
            Bytes::copy_from_slice(s.to_string_lossy().as_bytes())
        },
    }
}

fn ensure_sub_interpreter_initialized() {
    WORKER_INTERPRETER_STATE.with(|cell| {
        let tstate = *cell.borrow();
        if tstate.is_null() {
            unsafe {
                let config = ffi::PyInterpreterConfig {
                    use_main_obmalloc: 0,
                    allow_fork: 0,
                    allow_exec: 0,
                    allow_threads: 1,
                    allow_daemon_threads: 0,
                    check_multi_interp_extensions: 1,
                    gil: ffi::PyInterpreterConfig_OWN_GIL,
                };

                let mut new_interp: *mut ffi::PyThreadState = ptr::null_mut();
                let _ = ffi::Py_NewInterpreterFromConfig(&mut new_interp, &config);
                let py = Python::assume_attached();

                if let Ok(sys) = py.import("sys") {
                    if let Ok(path) = sys.getattr("path") {
                        if let Ok(cwd) = std::env::current_dir() {
                            let _ = path.call_method1("insert", (0, cwd.to_string_lossy()));
                        }
                    }
                }

                let mock_script = r#"
import sys, types
if 'turbox' not in sys.modules:
    m = types.ModuleType('turbox')
    m.Route = type('Route', (), {'add': lambda *args, **kwargs: None})
    m.Server = type('Server', (), {'bind': lambda *args: None, 'workers': lambda *args: None, 'config': lambda *args: None, 'run': lambda *args: None})
    m.Request = type('Request', (), {'json': lambda *args, **kwargs: None})
    m.Response = type('Response', (), {'json': lambda *args, **kwargs: None})
    sys.modules['turbox'] = m
    sys.modules['turbox.turbox'] = m
"#;
                let c_script = CString::new(mock_script).expect("Failed to create CString");
                if let Err(e) = py.run(&c_script, None, None) { e.print(py); }

                let suspended = ffi::PyEval_SaveThread();
                *cell.borrow_mut() = suspended;
            }
        }
    });
}

#[pyclass]
#[derive(Clone)]
pub struct Server {
    host: String,
    port: u16,
    workers: usize,
    max_connections: usize,
    backlog: u32,
    keep_alive: bool,
}

#[pymethods]
impl Server {
 
    #[new]
    pub fn new() -> Self {
        Server {
            host: "127.0.0.1".to_string(),
            port: 8000,
            workers: num_cpus::get(),
            max_connections: 100_000,
            backlog: 16 * 1024,
            keep_alive: true,
        }
    }
    pub fn bind(&mut self, host: String, port: u16) {
        self.host = host;
        self.port = port;
    }
    pub fn workers(&mut self, count: usize) {
        self.workers = if count == 0 { num_cpus::get() } else { count };
    }
    #[pyo3(signature = (max_connections=100_000, backlog=16384, keep_alive=true))]
    pub fn config(&mut self, max_connections: usize, backlog: u32, keep_alive: bool) {
        self.max_connections = max_connections;
        self.backlog = backlog;
        self.keep_alive = keep_alive;
    }
    pub fn run(&self, py: Python) -> PyResult<()> {
        let host = self.host.clone();
        let port = self.port;
        let workers = self.workers;
        let max_conns = self.max_connections;
        let backlog = self.backlog;
        let ka = self.keep_alive;

        py.detach(move || {
            let rt = tokio::runtime::Builder::new_multi_thread()
                .enable_all()
                .build()
                .expect("Failed to build Tokio runtime");

            rt.block_on(async {
                println!("🚀 Server running on http://{}:{} with {} workers", host, port, workers);
                let keep_alive_setting = if ka { KeepAlive::Os } else { KeepAlive::Disabled };

                HttpServer::new(|| {
                    App::new()
                        .default_service(web::to(actix_handler))
                })
                .workers(workers)
                .backlog(backlog)
                .keep_alive(keep_alive_setting)
                .max_connections(max_conns)
                .bind((host, port))
                .expect("Failed to bind to address")
                .run()
                .await
                .expect("Server error");
            });
        });

        Ok(())
    }

}

async fn actix_handler(req: HttpRequest, body: String) -> impl Responder {
    let method = req.method().as_str(); 
    let path = req.path();

    let route_cfg = if let Some(entry) = ROUTES.get(&(method.to_string(), path.to_string())) {
        Some(entry.value().clone())
    } else {
        None
    };

    if let Some(cfg) = route_cfg {
        ensure_sub_interpreter_initialized();

        let response_content = WORKER_INTERPRETER_STATE.with(|cell| {
            unsafe {
                let suspended = *cell.borrow();
                ffi::PyEval_RestoreThread(suspended);
                let py = Python::assume_attached();

                let ctx = PyDict::new(py);
                let _ = ctx.set_item("method", method);
                let _ = ctx.set_item("path", path);
                let _ = ctx.set_item("body", body);

                let headers_dict = PyDict::new(py);
                for (k, v) in req.headers().iter() {
                    let val = String::from_utf8_lossy(v.as_bytes());
                    let _ = headers_dict.set_item(k.as_str(), val);
                }
                let _ = ctx.set_item("headers", headers_dict);

                let result = FUNCTION_CACHE.with(|cache_cell| {
                    let mut cache = cache_cell.borrow_mut();

                    let exec_func = |h: Bound<'_, PyAny>| -> Bytes {
                        match h.call1((ctx,)) {
                            Ok(res) => {
                                if res.is_none() {
                                    return Bytes::new();
                                }
                                process_body(&res)
                            }
                            Err(e) => {
                                e.print(py);
                                Bytes::from_static(b"{\"error\": \"Internal Server Error\"}")
                            }
                        }
                    };

                    if let Some(cached) = cache.get(&cfg) {
                        exec_func(cached.bind(py).clone())
                    } else {
                        match PyModule::import(py, &*cfg.module) {
                            Ok(m) => match m.getattr(&*cfg.handler) {
                                Ok(func) => {
                                    let func_owned = func.clone().unbind();
                                    let res = exec_func(func);
                                    cache.insert(cfg, func_owned);
                                    res
                                }
                                Err(_) => Bytes::from(format!("Function '{}' not found in module '{}'", cfg.handler, cfg.module)),
                            },
                            Err(e) => {
                                e.print(py);
                                Bytes::from(format!("Module '{}' not found", cfg.module))
                            }
                        }
                    }
                });

                let new_suspended = ffi::PyEval_SaveThread();
                *cell.borrow_mut() = new_suspended;
                result
            }
        });

        HttpResponse::Ok().content_type("application/json").body(response_content)
    } else {
        HttpResponse::NotFound().body("Not Found")
    }
}
