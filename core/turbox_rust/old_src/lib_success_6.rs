use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer, Responder};
use pyo3::prelude::*;
use pyo3::ffi;
use pyo3::types::PyModule;
use std::sync::Mutex;
use std::collections::HashMap;
use std::ptr;
use std::cell::RefCell;
use lazy_static::lazy_static;

#[derive(Clone, Hash, PartialEq, Eq)]
struct RouteKey {
    module: String,
    handler: String,
}

lazy_static! {
    static ref ROUTES: Mutex<HashMap<(String, String), RouteKey>> = Mutex::new(HashMap::new());
}

// FIX 1: Use Py<PyAny> instead of PyObject (Deprecated)
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
                    
                    if let Some(cached_func) = cache.get(&cfg) {
                        // Fast Path: استدعاء من الكاش
                        let args = (body,);
                        // نستخدم bind(py) لأن الكائن مخزن كـ Py<PyAny> ويحتاج لربطه بالـ GIL
                        match cached_func.bind(py).call1(args) {
                            Ok(res) => res.extract::<String>().unwrap_or("Type Error".into()),
                            Err(e) => { e.print(py); "Runtime Error".to_string() }
                        }
                    } else {
                        // Slow Path: أول مرة فقط
                        let module = PyModule::import(py, &*cfg.module);
                        match module {
                            Ok(m) => {
                                let handler = m.getattr(&*cfg.handler);
                                match handler {
                                    Ok(func) => {
                                        // FIX 2: Clone before unbind
                                        // نقوم بنسخ المؤشر (رخيص جداً) لنصنع نسخة للكاش، ونحتفظ بالأصل للاستدعاء
                                        let func_for_cache = func.clone().unbind();
                                        
                                        let args = (body,);
                                        let res_str = match func.call1(args) {
                                            Ok(res) => res.extract::<String>().unwrap_or("Type Error".into()),
                                            Err(e) => { e.print(py); "Runtime Error".to_string() }
                                        };

                                        // تخزين النسخة في الكاش
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

        HttpResponse::Ok().body(response_content)
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

use actix_web::http::KeepAlive; // <--- تأكد من استيراد هذا
use std::time::Duration;

#[pyfunction]
fn run_server(py: Python, host: String, port: u16, workers: usize) -> PyResult<()> {
    py.detach(move || {
        // نستخدم Tokio Runtime لضمان بيئة Async قوية
        let rt = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .unwrap();

        rt.block_on(async {
            println!("🚀 TurboX (Tuned Edition) running on http://{}:{}", host, port);
            
            HttpServer::new(|| {
                App::new()
                    // إلغاء أي Middleware قد يضيف تأخيراً (نحن نظيفون بالفعل)
                    .default_service(web::to(request_handler))
            })
            // --- 1. توزيع الأحمال ---
            .workers(workers) // عدد الخيوط = عدد الكورز
            
            // --- 2. إعدادات الشبكة القصوى ---
            .backlog(100000) // زيادة حجم طابور الانتظار (Accept Queue) لاستيعاب الـ Spike
            .keep_alive(KeepAlive::Os) // استخدام الـ OS TCP KeepAlive لأقصى سرعة
            .max_connections(500_000) // فتح الحد الأقصى للاتصالات المتزامنة
            
            // --- 3. إلغاء القيود الزمنية (للـ Benchmarks فقط) ---
            .client_request_timeout(Duration::from_secs(0)) // لا تفصل العميل البطيء
            .client_disconnect_timeout(Duration::from_secs(0))
            
            // --- 4. الربط مع تحسينات Socket ---
            .bind((host, port))
            .expect("Failed to bind port")
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