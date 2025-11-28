use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer, Responder, rt};
use parking_lot::{RwLock, Mutex};
use pyo3::prelude::*;
use pyo3::types::PyString;
use pyo3::ffi;
use std::collections::HashMap;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::thread;
use crossbeam_channel::{bounded, Sender};
use tokio::sync::oneshot;

// --- 1. Global State ---
static ROUTER: OnceLock<RwLock<HashMap<String, (String, String)>>> = OnceLock::new();

fn get_router() -> &'static RwLock<HashMap<String, (String, String)>> {
    ROUTER.get_or_init(|| RwLock::new(HashMap::new()))
}

// --- 2. RSGI Objects (Pure Rust Structs initially) ---

#[pyclass(frozen)]
struct TurboSocket {
    tx: Mutex<Option<oneshot::Sender<String>>>,
}

#[pymethods]
impl TurboSocket {
    fn send(&self, body: String) {
        if let Some(tx) = self.tx.lock().take() {
            let _ = tx.send(body);
        }
    }
}

#[pyclass(frozen)]
struct TurboRequest {
    method: String,
    path: String,
}

#[pymethods]
impl TurboRequest {
    #[getter]
    fn method<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyString>> {
        Ok(PyString::new(py, &self.method))
    }
    #[getter]
    fn path<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyString>> {
        Ok(PyString::new(py, &self.path))
    }
}

// --- 3. The Job Definition ---
struct Job {
    module: String,
    handler: String,
    req: TurboRequest, // Rust struct sent across threads (Safe)
    tx: oneshot::Sender<String>,
}

// --- 4. Robust Sub-Interpreter Worker ---

fn spawn_worker(id: usize, rx: crossbeam_channel::Receiver<Job>) {
    thread::spawn(move || {
        println!("🔧 Worker #{} booting up...", id);

        // [STEP 1]: Create Interpreter & Release GIL
        // هذا المتغير سيحمل مؤشر الحالة الخاص بهذا الخيط
        let mut thread_state: *mut ffi::PyThreadState;

        unsafe {
            // أ) الحصول على الـ GIL الرئيسي للسماح بإنشاء مفسر
            let gstate = ffi::PyGILState_Ensure();
            
            // ب) إنشاء مفسر جديد (يملك الـ GIL الخاص به فوراً)
            thread_state = ffi::Py_NewInterpreter();
            
            if thread_state.is_null() {
                ffi::PyGILState_Release(gstate);
                panic!("Worker #{}: Failed to create interpreter", id);
            }

            // ج) إصلاح المسار (sys.path) ونحن نملك الـ GIL
            // نستخدم كتلة آمنة لضمان عدم انهيار الـ Unsafe
            let _ = std::panic::catch_unwind(|| {
                let _ = Python::with_gil(|py| {
                    if let Ok(sys) = py.import("sys") {
                        if let Ok(path) = sys.getattr("path") {
                            let _ = path.call_method1("append", (".",));
                        }
                    }
                });
            });

            // د) تحرير الـ GIL وحفظ الحالة (Save Thread)
            // الآن الخيط حر للانتظار في Rust بدون تجميد بايثون
            // PyEval_SaveThread ترجع المؤشر الحالي وتجعل الحالة NULL
            ffi::PyEval_SaveThread(); 
        }

        // [STEP 2]: Loop & Process
        while let Ok(job) = rx.recv() {
            unsafe {
                // هـ) استعادة الـ GIL لهذا المفسر (Restore Thread)
                // هذا يعيد تفعيل thread_state ويحجز القفل
                ffi::PyEval_RestoreThread(thread_state);
                
                // و) تنفيذ كود بايثون بأمان
                Python::with_gil(|py| {
                     let module = match PyModule::import(py, &*job.module) {
                        Ok(m) => m,
                        Err(e) => { e.print_and_set_sys_last_vars(py); return; }
                    };
                    
                    let handler = match module.getattr(&*job.handler) {
                        Ok(h) => h,
                        Err(e) => { e.print_and_set_sys_last_vars(py); return; }
                    };

                    // تحويل Rust Structs إلى Python Objects داخل هذا المفسر حصراً
                    let req_instance = Py::new(py, job.req).unwrap();
                    let sock_instance = Py::new(py, TurboSocket { tx: Mutex::new(Some(job.tx)) }).unwrap();

                    if let Err(e) = handler.call1((req_instance, sock_instance)) {
                        e.print_and_set_sys_last_vars(py);
                    }
                });

                // ز) تحرير الـ GIL مرة أخرى للعودة للانتظار
                // thread_state لا يتغير، لكننا نخبر بايثون أننا خرجنا
                ffi::PyEval_SaveThread();
            }
        }
        
        // تنظيف (لن يتم الوصول له غالباً في السيرفر المستمر)
        // unsafe {
        //     ffi::PyEval_RestoreThread(thread_state);
        //     ffi::Py_EndInterpreter(thread_state);
        // }
    });
}

// --- 5. Dispatcher System ---

static WORKER_CHANNELS: OnceLock<Vec<Sender<Job>>> = OnceLock::new();
static NEXT_WORKER: AtomicUsize = AtomicUsize::new(0);

fn init_workers(count: usize) {
    let mut senders = Vec::new();
    for id in 0..count {
        let (tx, rx) = bounded::<Job>(2048); // Buffer size
        senders.push(tx);
        spawn_worker(id, rx);
    }
    WORKER_CHANNELS.set(senders).ok();
}

fn dispatch_job(job: Job) -> Result<(), &'static str> {
    if let Some(channels) = WORKER_CHANNELS.get() {
        // Round Robin Atomic Dispatch
        let idx = NEXT_WORKER.fetch_add(1, Ordering::Relaxed) % channels.len();
        // Send and forget (Worker handles it)
        channels[idx].send(job).map_err(|_| "Worker disconnected")
    } else {
        Err("No workers")
    }
}

// --- 6. The Handler ---

async fn async_handler(req: HttpRequest) -> impl Responder {
    let path = req.path().to_string();
    let method = req.method().to_string();

    let route_info = {
        let router = get_router().read();
        router.get(&path).cloned()
    };

    if let Some((module_name, func_name)) = route_info {
        let (tx, rx) = oneshot::channel::<String>();

        let job = Job {
            module: module_name,
            handler: func_name,
            req: TurboRequest { method, path },
            tx,
        };

        if dispatch_job(job).is_ok() {
            match rx.await {
                Ok(body) => HttpResponse::Ok().body(body),
                Err(_) => HttpResponse::InternalServerError().body("Worker Timeout"),
            }
        } else {
            HttpResponse::ServiceUnavailable().body("System Overload")
        }
    } else {
        HttpResponse::NotFound().body("Not Found")
    }
}

// --- 7. Python DSL ---

#[pyfunction]
fn add_route(path: String, module: String, handler_name: String) {
    let mut router = get_router().write();
    router.insert(path, (module, handler_name));
}

#[pyfunction]
fn run_server(py: Python<'_>, host: String, port: u16, workers: usize) -> PyResult<()> {
    println!("🔥 TurboX Engine (Stable Sub-Interpreters) Starting...");
    
    // 1. Init Workers Pool (Warm Start)
    init_workers(workers);

    // 2. Run Actix (Detach Main Python Thread)
    Python::detach(py, || {
        let sys = actix_rt::System::new();
        sys.block_on(async move {
            HttpServer::new(|| {
                App::new()
                    .default_service(web::to(async_handler))
            })
            .workers(workers) // IO Threads matches Worker Threads usually
            .bind((host, port))
            .expect("Bind failed")
            .run()
            .await
            .expect("Server crash");
        });
    });

    Ok(())
}

#[pymodule]
fn turbox(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(add_route, m)?)?;
    m.add_function(wrap_pyfunction!(run_server, m)?)?;
    Ok(())
}