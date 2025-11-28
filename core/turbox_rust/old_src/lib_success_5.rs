use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer, Responder};
use pyo3::prelude::*;
use pyo3::ffi;
use pyo3::types::PyModule;
use std::sync::Mutex;
use std::collections::HashMap;
use std::ptr;
use std::cell::RefCell;
use lazy_static::lazy_static;

#[derive(Clone)]
struct RouteConfig {
    module: String,
    handler: String,
}

lazy_static! {
    static ref ROUTES: Mutex<HashMap<(String, String), RouteConfig>> = Mutex::new(HashMap::new());
}

// نخزن حالة الثريد وهو "محرر" (Released/Saved)
thread_local! {
    static WORKER_INTERPRETER_STATE: RefCell<*mut ffi::PyThreadState> = RefCell::new(ptr::null_mut());
}

fn ensure_sub_interpreter_initialized() {
    WORKER_INTERPRETER_STATE.with(|cell| {
        let tstate = *cell.borrow();
        if tstate.is_null() {
            unsafe {
                // 1. الحصول على الحالة الرئيسية وحفظها للرجوع إليها لاحقاً إذا لزم الأمر
                // (في حالتنا، نحن ننشئ بيئة منعزلة لكل خيط)
                
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
                
                // هذه الدالة تنشئ المفسر وتجعله "الحالي" وتمسك الـ GIL الخاص به
                let status = ffi::Py_NewInterpreterFromConfig(&mut new_interp, &config);
                
                if ffi::PyStatus_Exception(status) != 0 || new_interp.is_null() {
                    panic!("CRITICAL: Failed to create Sub-Interpreter");
                }
                
                println!("🔧 Worker {:?} Created Interpreter. Initializing...", std::thread::current().id());

                // 2. الحركة الذكية:
                // نحن الآن نمسك الـ GIL. ولكننا نريد العودة لـ Rust (Actix loop).
                // لذا نقوم بعمل "SaveThread". هذا يفك الـ GIL ويعطينا مؤشراً لحالة الانتظار.
                let suspended_state = ffi::PyEval_SaveThread();
                
                // نخزن هذه الحالة "المعلقة"
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
        // تأكد من الإنشاء (مرة واحدة لكل خيط)
        ensure_sub_interpreter_initialized();

        let response_content = WORKER_INTERPRETER_STATE.with(|cell| {
            unsafe {
                let suspended_state = *cell.borrow();
                
                // 3. الدخول الآمن: RestoreThread
                // هذه الدالة تقوم بأمرين:
                // أ. تجعل المفسر الحالي هو مفسرنا.
                // ب. تقوم بعمل Lock للـ GIL الخاص بهذا المفسر.
                ffi::PyEval_RestoreThread(suspended_state);
                
                // نحن الآن نملك الـ GIL ونستطيع استخدام PyO3 بأمان
                let py = Python::assume_attached();
                
                let result = {
                    let module = PyModule::import(py, &*cfg.module);
                    match module {
                        Ok(m) => {
                            let handler = m.getattr(&*cfg.handler);
                            match handler {
                                Ok(func) => {
                                    let args = (body,);
                                    match func.call1(args) {
                                        Ok(res) => res.extract::<String>().unwrap_or("Type Error".into()),
                                        Err(e) => {
                                            e.print(py);
                                            "Handler Runtime Error".to_string()
                                        }
                                    }
                                },
                                Err(_) => "Function not found".to_string(),
                            }
                        },
                        Err(e) => {
                            e.print(py);
                            format!("Failed to import module '{}'", cfg.module)
                        }
                    }
                };

                // 4. الخروج الآمن: SaveThread
                // نفك الـ GIL ونعود لوضع التعليق قبل الرجوع لـ Actix
                // المؤشر قد يتغير أحياناً لذا نقوم بتحديثه
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
    routes.insert((method, path), RouteConfig { module: module_name, handler: func_name });
    Ok(())
}

#[pyfunction]
fn run_server(py: Python, host: String, port: u16, workers: usize) -> PyResult<()> {
    // نفصل الثريد الرئيسي (Main Interpreter) للسماح بتشغيل السيرفر
    py.detach(move || {
        let rt = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .unwrap();

        rt.block_on(async {
            println!("🚀 TurboX running on http://{}:{}", host, port);
            HttpServer::new(|| {
                App::new().default_service(web::to(request_handler))
            })
            .workers(workers)
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