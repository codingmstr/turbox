use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer, Responder};
use pyo3::prelude::*;
use pyo3::ffi;
use pyo3::types::{PyModule, PyString, PyDict, PyBool, PyBytes, PyTuple}; 
use std::collections::HashMap;
use std::ptr;
use std::cell::RefCell;
use lazy_static::lazy_static;
use pythonize::depythonize;
use serde_json::Value;
use actix_web::http::KeepAlive;
use dashmap::DashMap;
use mimalloc::MiMalloc;
use bytes::Bytes;

#[global_allocator]
static GLOBAL: MiMalloc = MiMalloc;

#[derive(Clone, Hash, PartialEq, Eq)]
struct RouteKey {
    module: String,
    handler: String,
}

lazy_static! {
    static ref ROUTES: DashMap<(String, String), RouteKey> = DashMap::new();
}

thread_local! {
    static WORKER_INTERPRETER_STATE: RefCell<*mut ffi::PyThreadState> = RefCell::new(ptr::null_mut());
    static FUNCTION_CACHE: RefCell<HashMap<RouteKey, Py<PyAny>>> = RefCell::new(HashMap::new());
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
                let suspended = ffi::PyEval_SaveThread();
                *cell.borrow_mut() = suspended;
            }
        }
    });
}

fn process_body(obj: &Bound<'_, PyAny>) -> Bytes {
    if let Ok(s) = obj.cast::<PyString>() {
        return Bytes::copy_from_slice(s.to_string_lossy().as_bytes());
    }
    
    if let Ok(b) = obj.cast::<PyBool>() {
        return if b.is_true() { Bytes::from_static(b"true") } else { Bytes::from_static(b"false") };
    }

    if let Ok(b) = obj.cast::<PyBytes>() {
        return Bytes::copy_from_slice(b.as_bytes());
    }

    match depythonize::<Value>(obj) {
        Ok(v) => Bytes::from(serde_json::to_vec(&v).unwrap_or_default()),
        Err(_) => Bytes::from(obj.to_string().into_bytes()),
    }
}

async fn request_handler(req: HttpRequest, body: String) -> impl Responder {
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
                                Err(_) => Bytes::from(format!("Function '{}' not found", cfg.handler)),
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

        HttpResponse::Ok()
            .content_type("application/json")
            .body(response_content)
    } else {
        HttpResponse::NotFound().body("Not Found")
    }
}

#[pyfunction]
fn add_route(_py: Python, method: String, path: String, handler: Bound<'_, PyAny>) -> PyResult<()> {
    let func_name: String = handler.getattr("__name__")?.extract()?;
    let mod_name: String = handler.getattr("__module__")?.extract()?;
    ROUTES.insert((method, path), RouteKey { module: mod_name, handler: func_name });
    Ok(())
}

#[pyfunction]
fn run_server(py: Python, host: String, port: u16, workers: usize) -> PyResult<()> {
    py.detach(move || {
        let rt = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .unwrap();

        rt.block_on(async {
            println!("🚀 TurboX running on http://{}:{}", host, port);
            println!("🔒 Mode: Stable Dynamic (Depythonize + Bytes Optimized)");

            HttpServer::new(|| App::new().default_service(web::to(request_handler)))
                .workers(workers)
                .backlog(1024 * 16)
                .keep_alive(KeepAlive::Os)
                .max_connections(100_000)
                .bind((host, port))
                .unwrap()
                .run()
                .await
                .unwrap();
        });
    });
    Ok(())
}

#[pymodule]
fn turbox(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(add_route, m)?)?;
    m.add_function(wrap_pyfunction!(run_server, m)?)?;
    Ok(())
}
