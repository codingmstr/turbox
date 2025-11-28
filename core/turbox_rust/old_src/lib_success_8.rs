use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer, Responder};
use pyo3::prelude::*;
use pyo3::ffi;
use pyo3::types::{PyModule, PyString};
use std::sync::Mutex;
use std::collections::HashMap;
use std::ptr;
use std::cell::RefCell;
use lazy_static::lazy_static;
use pythonize::depythonize;
use serde_json::Value;
use actix_web::http::KeepAlive;
use std::time::Duration;

// ----------------------------------------------------------------
//  NEW: The Wrapper Struct (Zero-Copy Proxy)
// ----------------------------------------------------------------
#[pyclass]
struct RequestContext {
    // نخزن العنوان فقط كرقم، لتجنب تعقيدات الـ Lifetimes مع PyO3
    req_ptr: usize, 
}

#[pymethods]
impl RequestContext {
    // دالة لاسترجاع الـ Path
    fn path(&self) -> String {
        unsafe {
            // تحويل الرقم لعنوان حقيقي
            let req = &*(self.req_ptr as *const HttpRequest); 
            req.path().to_string()
        }
    }

    // دالة لاسترجاع الـ Method
    fn method(&self) -> String {
        unsafe {
            let req = &*(self.req_ptr as *const HttpRequest);
            req.method().as_str().to_string()
        }
    }

    // دالة لاسترجاع Header معين
    fn header(&self, key: String) -> Option<String> {
        unsafe {
            let req = &*(self.req_ptr as *const HttpRequest);
            req.headers()
                .get(&key)
                .and_then(|v| v.to_str().ok())
                .map(|s| s.to_string())
        }
    }
}
// ----------------------------------------------------------------

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

                let suspended_state = ffi::PyEval_SaveThread();
                *cell.borrow_mut() = suspended_state;
            }
        }
    });
}

async fn request_handler(req: HttpRequest, body: String) -> impl Responder {
    let method = req.method().as_str();
    let path = req.path();

    let route_cfg = {
        let routes = ROUTES.lock().unwrap();
        routes.get(&(method.to_string(), path.to_string())).cloned()
    };

    if let Some(cfg) = route_cfg {
        ensure_sub_interpreter_initialized();

        let response_content = WORKER_INTERPRETER_STATE.with(|cell| {
            unsafe {
                let suspended_state = *cell.borrow();
                ffi::PyEval_RestoreThread(suspended_state);
                let py = Python::assume_attached();
                
                let result = FUNCTION_CACHE.with(|cache_cell| {
                    let mut cache = cache_cell.borrow_mut();
                    
                    let execute_and_convert = |handler: Bound<'_, PyAny>| -> String {
                        // ---------------------------------------------------------
                        // التعديل الجوهري هنا: تمرير الـ Pointer بدلاً من النسخ
                        // ---------------------------------------------------------
                        // 1. نأخذ عنوان الذاكرة للريكويست الحالي
                        let req_ptr = &req as *const HttpRequest as usize;
                        
                        // 2. ننشئ الكائن الوسيط (Context Object)
                        // ملاحظة: Bound::new ينشئ الكائن داخل مفسر بايثون الحالي (Sub-Interpreter)
                        let context_obj = match Bound::new(py, RequestContext { req_ptr }) {
                            Ok(obj) => obj,
                            Err(e) => {
                                e.print(py);
                                return "{\"error\": \"Context Creation Failed\"}".to_string();
                            }
                        };

                        // 3. نمرر الكائن + البودي كـ Tuple
                        let args = (context_obj, body.clone());
                        
                        match handler.call1(args) {
                            Ok(res) => {
                                if let Ok(s) = res.cast::<PyString>() {
                                    s.to_string()
                                } 
                                else {
                                    match depythonize::<Value>(&res) {
                                        Ok(val) => val.to_string(),
                                        Err(_) => res.to_string(),
                                    }
                                }
                            },
                            Err(e) => {
                                e.print(py);
                                "{\"error\": \"Internal Server Error\"}".to_string()
                            }
                        }
                    };

                    if let Some(cached_func) = cache.get(&cfg) {
                        execute_and_convert(cached_func.bind(py).clone())
                    } else {
                        let module = PyModule::import(py, &*cfg.module);
                        match module {
                            Ok(m) => {
                                let handler = m.getattr(&*cfg.handler);
                                match handler {
                                    Ok(func) => {
                                        let func_for_cache = func.clone().unbind();
                                        let res_str = execute_and_convert(func);
                                        cache.insert(cfg, func_for_cache);
                                        res_str
                                    },
                                    Err(_) => format!("Function '{}' not found", cfg.handler),
                                }
                            },
                            Err(e) => { e.print(py); format!("Module '{}' not found", cfg.module) }
                        }
                    }
                });

                let new_suspended_state = ffi::PyEval_SaveThread();
                *cell.borrow_mut() = new_suspended_state;

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
    let module_name: String = handler.getattr("__module__")?.extract()?;

    let mut routes = ROUTES.lock().unwrap();
    routes.insert((method, path), RouteKey { module: module_name, handler: func_name });
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
            println!("🚀 TurboX (Pointer Context Edition) running on http://{}:{}", host, port);
            
            HttpServer::new(|| {
                App::new().default_service(web::to(request_handler))
            })
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
    // يجب تسجيل الكلاس الجديد هنا ليعرفه بايثون
    m.add_class::<RequestContext>()?;
    m.add_function(wrap_pyfunction!(add_route, m)?)?;
    m.add_function(wrap_pyfunction!(run_server, m)?)?;
    Ok(())
}