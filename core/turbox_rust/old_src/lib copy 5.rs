use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer};
use actix_web::http::KeepAlive;
use bytes::Bytes;
use mimalloc::MiMalloc;
use pyo3::prelude::*;
use pyo3::types::{PyModule, PyString, PyBytes};
use socket2::{Domain, Protocol, Socket, Type};
use std::cell::RefCell;
use std::net::TcpListener;
use std::process;
use std::thread;
use std::time::Duration;
use tokio::runtime::Runtime;

#[global_allocator]
static GLOBAL: MiMalloc = MiMalloc;

// =========================================================
//  Context Pooling (Thread-Local & Fast)
// =========================================================

thread_local! {
    static CACHED_HANDLER: RefCell<Option<Py<PyAny>>> = RefCell::new(None);
    static CONTEXT_POOL: RefCell<Vec<Py<TurboContext>>> = RefCell::new(Vec::with_capacity(2048));
}

// [CRITICAL OPTIMIZATION]: unsendable
// هذا يزيل overhead الـ Send/Sync checks والـ Atomics
// يسمح لنا باستخدام std::cell::RefCell بدلاً من Mutex
#[pyclass(unsendable)]
struct TurboContext {
    _path: RefCell<String>,
    _body: RefCell<Bytes>,
    
    response_status: RefCell<u16>,
    response_body: RefCell<Bytes>,
}

#[pymethods]
impl TurboContext {
    #[new]
    fn new() -> Self {
        TurboContext {
            // حجز مسبق للذاكرة لتقليل التخصيص لاحقاً
            _path: RefCell::new(String::with_capacity(128)),
            _body: RefCell::new(Bytes::new()),
            response_status: RefCell::new(200),
            response_body: RefCell::new(Bytes::new()),
        }
    }

    #[getter]
    fn path<'py>(&self, py: Python<'py>) -> Bound<'py, PyString> {
        // No Mutex lock overhead here, just pointer chasing
        PyString::new(py, &self._path.borrow())
    }

    #[getter]
    fn body<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self._body.borrow())
    }

    #[pyo3(signature = (status, body))]
    fn respond(&self, status: u16, body: &Bound<'_, PyAny>) {
        *self.response_status.borrow_mut() = status;
        
        let bytes = if let Ok(s) = body.extract::<String>() {
            Bytes::from(s)
        } else if let Ok(b) = body.cast::<PyBytes>() {
            Bytes::copy_from_slice(b.as_bytes())
        } else {
            Bytes::from(body.to_string())
        };
        
        *self.response_body.borrow_mut() = bytes;
    }
}

impl TurboContext {
    fn reset(&self, path: &str, body: Bytes) {
        // Reuse String buffer
        let mut p = self._path.borrow_mut();
        p.clear();
        p.push_str(path); 

        *self._body.borrow_mut() = body;
        *self.response_status.borrow_mut() = 200;
        // Note: We overwrite response_body later, no need to clear usually, 
        // but strictly speaking we should if logic depended on empty.
        // For speed, we overwrite.
    }
}

// =========================================================
//  Handler
// =========================================================
async fn handler(req: HttpRequest, body: Bytes) -> HttpResponse {
    // Actix path() returns &str reference (Zero Copy)
    let path = req.path();
    
    let (status, resp_bytes) = Python::attach(|py| {
        CACHED_HANDLER.with(|cell| {
            let mut handler_opt = cell.borrow_mut();

            // 1. Lazy Import
            if handler_opt.is_none() {
                let module = PyModule::import(py, "handlers").expect("Failed to import handlers");
                let func = module.getattr("app").expect("Failed to find 'app'");
                *handler_opt = Some(func.into());
            }
            let app_func = handler_opt.as_ref().unwrap();

            // 2. Pool Management (No Atomics!)
            CONTEXT_POOL.with(|pool_cell| {
                let mut pool = pool_cell.borrow_mut();
                
                let py_ctx_obj = if let Some(existing) = pool.pop() {
                    // Resetting RefCell is incredibly fast (non-atomic)
                    existing.borrow(py).reset(path, body);
                    existing
                } else {
                    // Cold start creation
                    let ctx = TurboContext::new();
                    ctx.reset(path, body);
                    Py::new(py, ctx).unwrap()
                };

                // 3. Call Python
                if let Err(e) = app_func.call1(py, (py_ctx_obj.clone_ref(py),)) {
                    e.print_and_set_sys_last_vars(py);
                    // Recycle even on error
                    pool.push(py_ctx_obj);
                    return (500, Bytes::from("Internal Python Error"));
                }

                // 4. Extract Response
                let (s, b) = {
                    // Borrowing RefCell is cheap
                    let ctx_ref = py_ctx_obj.borrow(py);
                    let s = *ctx_ref.response_status.borrow();
                    let b = ctx_ref.response_body.borrow().clone();
                    (s, b)
                };
                
                // 5. Recycle
                pool.push(py_ctx_obj);

                (s, b)
            })
        })
    });

    let mut builder = HttpResponse::build(actix_web::http::StatusCode::from_u16(status).unwrap());
    builder.body(resp_bytes)
}

// =========================================================
//  Worker Logic
// =========================================================
fn spawn_worker(host: String, port: u16) {
    unsafe {
        let pid = libc::fork();
        if pid < 0 {
            process::exit(1);
        }

        if pid == 0 {
            // Child Process Optimization
            let domain = Domain::IPV4;
            let socket = Socket::new(domain, Type::STREAM, Some(Protocol::TCP)).unwrap();
            
            let _ = socket.set_reuse_address(true);
            let _ = socket.set_reuse_port(true);
            let _ = socket.set_nodelay(true);
            // Massive buffers for 200k throughput
            let _ = socket.set_recv_buffer_size(1024 * 256);
            let _ = socket.set_send_buffer_size(1024 * 256);

            let address = format!("{}:{}", host, port).parse::<std::net::SocketAddr>().unwrap();
            socket.bind(&address.into()).unwrap();
            // Maximum backlog allowed by typical Linux tuning
            socket.listen(100_000).unwrap(); 

            let listener: TcpListener = socket.into();

            Python::attach(|py| {
                let sys = py.import("sys").unwrap();
                let path = sys.getattr("path").unwrap();
                let _ = path.call_method1("append", (".",));
                let _ = PyModule::import(py, "handlers"); 

                Python::detach(py, || {
                    // Current Thread Runtime is ideal for 1-core-per-process
                    let rt = tokio::runtime::Builder::new_current_thread()
                        .enable_all()
                        .build()
                        .unwrap();

                    rt.block_on(async move {
                        HttpServer::new(|| {
                            App::new()
                                .default_service(web::to(handler))
                        })
                        .listen(listener).unwrap()
                        .workers(1) 
                        .backlog(100_000)
                        .keep_alive(KeepAlive::Os)
                        .max_connections(250_000)
                        .client_request_timeout(Duration::from_secs(0)) // Disable timeout checks for max raw speed
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
fn run_server(_py: Python<'_>, host: String, port: u16, workers: usize) -> PyResult<()> {
    unsafe { libc::signal(libc::SIGCHLD, libc::SIG_IGN); }

    println!("🔥 TurboX V6 (Unsendable/Non-Atomic) Starting...");
    println!("   Host: {}:{}", host, port);
    println!("   Workers: {}", workers);

    for _ in 0..workers {
        spawn_worker(host.clone(), port);
    }

    loop {
        thread::sleep(Duration::from_secs(3600));
    }

    #[allow(unreachable_code)]
    Ok(())
}

#[pymodule]
fn turbox(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_server, m)?)?;
    m.add_class::<TurboContext>()?;
    Ok(())
}