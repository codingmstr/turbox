use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer, Responder};
use pyo3::prelude::*;
use pyo3::ffi;
use pyo3::types::{PyModule, PyString, PyDict};
use pyo3::types::PyAnyMethods;
use std::sync::Mutex;
use std::collections::HashMap;
use std::ptr;
use std::cell::RefCell;
use lazy_static::lazy_static;
use pythonize::depythonize;
use serde_json::Value;
use actix_web::http::KeepAlive;
use std::time::Duration;

#[derive(Clone, Hash, PartialEq, Eq)]
struct RouteKey {
    module: String,
    handler: String,
}

lazy_static! {
    static ref ROUTES: Mutex<HashMap<(String, String), RouteKey>> = Mutex::new(HashMap::new());
}

thread_local! {
    static WORKER_INTERPRETER_STATE: RefCell<*mut ffi::PyThreadState> = RefCell::new(ptr::null_mut());
    static FUNCTION_CACHE: RefCell<HashMap<RouteKey, Py<PyAny>>> = RefCell::new(HashMap::new());
}

// -----------------------------------------------------------
//  SUB-INTERPRETER INITIALIZER (PER WORKER)
// -----------------------------------------------------------
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
                let status = ffi::Py_NewInterpreterFromConfig(&mut new_interp, &config);

                if ffi::PyStatus_Exception(status) != 0 || new_interp.is_null() {
                    panic!("CRITICAL: Failed to create Sub-Interpreter");
                }

                let py = Python::assume_attached();
                if let Ok(sys) = py.import("sys") {
                    if let Ok(path) = sys.getattr("path") {
                        let cwd = std::env::current_dir().unwrap();
                        let cwd_str = cwd.to_str().unwrap();
                        let _ = path.call_method1("insert", (0, cwd_str));
                    }
                }

                let suspended = ffi::PyEval_SaveThread();
                *cell.borrow_mut() = suspended;
            }
        }
    });
}

// -----------------------------------------------------------
//  REQUEST HANDLER
// -----------------------------------------------------------
async fn request_handler(req: HttpRequest, body: String) -> impl Responder {
    let method = req.method().as_str().to_string();
    let path = req.path().to_string();

    let route_cfg = {
        let routes = ROUTES.lock().unwrap();
        routes.get(&(method.clone(), path.clone())).cloned()
    };

    if let Some(cfg) = route_cfg {
        ensure_sub_interpreter_initialized();

        let response_content = WORKER_INTERPRETER_STATE.with(|cell| {
            unsafe {
                let suspended = *cell.borrow();
                ffi::PyEval_RestoreThread(suspended);

                let py = Python::assume_attached();

                // ----------- BUILD CONTEXT DICT ----------- 
                let ctx = PyDict::new(py);
                ctx.set_item("method", method.clone()).unwrap();
                ctx.set_item("path", path.clone()).unwrap();
                ctx.set_item("body", body.clone()).unwrap();

                let headers_dict = PyDict::new(py);
                for (k, v) in req.headers().iter() {
                    if let Ok(val) = v.to_str() {
                        headers_dict.set_item(k.as_str(), val).unwrap();
                    }
                }
                ctx.set_item("headers", headers_dict).unwrap();
                // -------------------------------------------------

                let result = FUNCTION_CACHE.with(|cache_cell| {
                    let mut cache = cache_cell.borrow_mut();

                    let exec_func = |h: Bound<'_, PyAny>| -> String {
                        let args = (ctx,);

                        match h.call1(args) {
                            Ok(res) => {
                                if res.is_none() {
                                    return "{}".to_string();
                                }

                                if let Ok(s) = res.cast::<PyString>() {
                                    return format!("\"{}\"", s.to_string());
                                }

                                match depythonize::<Value>(&res) {
                                    Ok(v) => v.to_string(),
                                    Err(_) => res.to_string(),
                                }
                            }
                            Err(e) => {
                                e.print(py);
                                "{\"error\": \"Internal Server Error\"}".to_string()
                            }
                        }
                    };

                    if let Some(cached) = cache.get(&cfg) {
                        exec_func(cached.bind(py).clone())
                    } else {
                        let module = PyModule::import(py, &*cfg.module);
                        match module {
                            Ok(m) => {
                                let handler = m.getattr(&*cfg.handler);
                                match handler {
                                    Ok(func) => {
                                        let func_for_cache = func.clone().unbind();
                                        let res_str = exec_func(func);
                                        cache.insert(cfg, func_for_cache);
                                        res_str
                                    }
                                    Err(_) => format!("Function '{}' not found", cfg.handler),
                                }
                            }
                            Err(e) => {
                                e.print(py);
                                format!("Module '{}' not found", cfg.module)
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

// -----------------------------------------------------------
//  PYTHON API
// -----------------------------------------------------------
#[pyfunction]
fn add_route(_py: Python, method: String, path: String, handler: Bound<'_, PyAny>) -> PyResult<()> {
    let func_name: String = handler.getattr("__name__")?.extract()?;
    let mod_name: String = handler.getattr("__module__")?.extract()?;

    let mut routes = ROUTES.lock().unwrap();
    routes.insert((method, path), RouteKey { module: mod_name, handler: func_name });

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

            HttpServer::new(|| App::new().default_service(web::to(request_handler)))
                .workers(workers)
                .backlog(100_000)
                .keep_alive(KeepAlive::Os)
                .max_connections(500_000)
                .client_request_timeout(Duration::from_secs(0))
                .client_disconnect_timeout(Duration::from_secs(0))
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
