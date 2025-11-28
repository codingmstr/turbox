use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer};
use actix_web::http::KeepAlive;
use bytes::Bytes;
use mimalloc::MiMalloc;
use pyo3::prelude::*;
use pyo3::types::{PyModule, PyString};
use socket2::{Domain, Protocol, Socket, Type};
use std::cell::RefCell;
use std::net::TcpListener;
use std::os::fd::{AsRawFd, FromRawFd};
use std::process;
use std::thread;
use std::time::Duration;
use tokio::runtime::Runtime;

// تفعيل Mimalloc
#[global_allocator]
static GLOBAL: MiMalloc = MiMalloc;

// تخزين الدالة محلياً
thread_local! {
    static CACHED_HANDLER: RefCell<Option<Py<PyAny>>> = RefCell::new(None);
}

// =========================================================
//  Handler
// =========================================================
async fn handler(req: HttpRequest, body: Bytes) -> HttpResponse {
    let path = req.path();
    // Zero-copy conversion attempt (Unsafe fast path)
    let body_str = unsafe { std::str::from_utf8_unchecked(&body) };

    let response_content = Python::with_gil(|py| {
        CACHED_HANDLER.with(|cell| {
            let mut handler_opt = cell.borrow_mut();

            if handler_opt.is_none() {
                let module = PyModule::import(py, "handlers").expect("Import failed");
                let func = module.getattr("app").expect("Function not found");
                *handler_opt = Some(func.into());
            }

            let app_func = handler_opt.as_ref().unwrap();
            
            match app_func.call1(py, (path, body_str)) {
                Ok(res) => {
                    if let Ok(s) = res.extract::<String>(py) {
                        Bytes::from(s)
                    } else {
                        Bytes::from_static(b"Type Error")
                    }
                }
                Err(e) => {
                    e.print_and_set_sys_last_vars(py);
                    Bytes::from_static(b"500 Error")
                }
            }
        })
    });

    HttpResponse::Ok().body(response_content)
}

// =========================================================
//  Worker Spawner with CPU Affinity
// =========================================================
fn spawn_worker(listener_fd: i32, worker_index: usize, core_ids: &Vec<core_affinity::CoreId>) {
    unsafe {
        let pid = libc::fork();

        if pid < 0 {
            eprintln!("❌ fork() failed");
            process::exit(1);
        }

        if pid == 0 {
            // --- CHILD PROCESS START ---
            
            // [CRITICAL]: Pin this process to a specific CPU Core
            // نستخدم المعامل worker_index لتوزيع العمليات على الأنوية بالتساوي
            if let Some(core_id) = core_ids.get(worker_index % core_ids.len()) {
                core_affinity::set_for_current(*core_id);
                // println!("📌 Worker {} pinned to Core {:?}", worker_index, core_id);
            }

            let listener = TcpListener::from_raw_fd(listener_fd);

            Python::with_gil(|py| {
                // Warm up imports
                let sys = py.import("sys").unwrap();
                let path = sys.getattr("path").unwrap();
                let _ = path.call_method1("append", (".",));
                let _ = PyModule::import(py, "handlers"); // Pre-load user code

                Python::detach(py, || {
                    let rt = Runtime::new().unwrap();
                    rt.block_on(async move {
                        HttpServer::new(|| {
                            App::new().default_service(web::to(handler))
                        })
                        .listen(listener)
                        .unwrap()
                        .workers(1) // خيط واحد لأننا حجزنا النواة بالكامل لهذه العملية
                        .backlog(65535) // رفع الـ Backlog للأقصى
                        .keep_alive(KeepAlive::Os)
                        .max_connections(200_000)
                        .run()
                        .await
                        .unwrap();
                    });
                });
            });

            process::exit(0);
        }
    }
}

#[pyfunction]
fn run_server(py: Python<'_>, host: String, port: u16, workers: usize) -> PyResult<()> {
    // 1. Setup Listener
    let listener = TcpListener::bind((host.as_str(), port))
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Bind failed: {e}")))?;

    listener.set_nonblocking(true)
        .map_err(|_| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Non-blocking failed"))?;

    let listener_fd = listener.as_raw_fd();

    // 2. Detect CPU Cores for Pinning
    // نحصل على قائمة الأنوية المتاحة لنقوم بتوزيع العمال عليها
    let core_ids = core_affinity::get_core_ids().unwrap_or_else(|| Vec::new());
    println!("🖥️  Detected {} CPU Cores", core_ids.len());

    // 3. Handle Signals
    unsafe { libc::signal(libc::SIGCHLD, libc::SIG_IGN); }

    println!("🔥 TurboX V3 Extreme (Affinity + Mimalloc)");
    println!("   Host: {}:{}", host, port);
    println!("   Workers: {}", workers);

    // 4. Spawn Workers
    for i in 0..workers {
        spawn_worker(listener_fd, i, &core_ids);
    }

    // 5. Master Loop
    loop {
        thread::sleep(Duration::from_secs(3600));
    }

    #[allow(unreachable_code)]
    Ok(())
}

#[pymodule]
fn turbox(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_server, m)?)?;
    Ok(())
}