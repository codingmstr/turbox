use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer};
use actix_web::http::KeepAlive;
use bytes::Bytes;
use mimalloc::MiMalloc;
use parking_lot::Mutex; // Thread-safe replacement for RefCell
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

// Thread-local storage for caching Python handlers (per thread)
thread_local! {
    static CACHED_HANDLER: RefCell<Option<Py<PyAny>>> = RefCell::new(None);
}

// =========================================================
//  Lazy Context Object (Thread-Safe Fix)
// =========================================================

#[pyclass]
struct TurboContext {
    // Immutable raw data
    _path: String,
    _body: Bytes,
    
    // Mutable state protected by a fast Mutex (Sync + Send)
    // This fixes the "RefCell cannot be shared" error
    response_status: Mutex<u16>,
    response_body: Mutex<Bytes>,
}

#[pymethods]
impl TurboContext {
    #[getter]
    fn path<'py>(&self, py: Python<'py>) -> Bound<'py, PyString> {
        PyString::new(py, &self._path)
    }

    #[getter]
    fn body<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self._body)
    }

    #[pyo3(signature = (status, body))]
    fn respond(&self, status: u16, body: &Bound<'_, PyAny>) {
        // Lock and update status
        *self.response_status.lock() = status;
        
        // Optimized conversion
        let bytes = if let Ok(s) = body.extract::<String>() {
            Bytes::from(s)
        } else if let Ok(b) = body.cast::<PyBytes>() { // Fixed: downcast -> cast
            Bytes::copy_from_slice(b.as_bytes())
        } else {
            Bytes::from(body.to_string())
        };
        
        // Lock and update body
        *self.response_body.lock() = bytes;
    }
}

// =========================================================
//  Handler
// =========================================================
async fn handler(req: HttpRequest, body: Bytes) -> HttpResponse {
    let path = req.path();
    
    // Initialize context with default 200 OK
    let context_data = TurboContext {
        _path: path.to_string(),
        _body: body,
        response_status: Mutex::new(200),
        response_body: Mutex::new(Bytes::new()),
    };

    // Fixed: with_gil -> attach
    let (status, resp_bytes) = Python::attach(|py| {
        CACHED_HANDLER.with(|cell| {
            let mut handler_opt = cell.borrow_mut();

            if handler_opt.is_none() {
                let module = PyModule::import(py, "handlers").expect("Failed to import handlers");
                let func = module.getattr("app").expect("Failed to find 'app'");
                *handler_opt = Some(func.into());
            }

            let app_func = handler_opt.as_ref().unwrap();
            
            let py_context = Py::new(py, context_data).unwrap();
            
            if let Err(e) = app_func.call1(py, (py_context.clone_ref(py),)) {
                e.print_and_set_sys_last_vars(py);
                return (500, Bytes::from("Internal Python Error"));
            }

            // Read the response from the Mutexes
            // We borrow the PyObject to get the Rust struct reference
            let ctx_ref = py_context.borrow(py);
            let s = *ctx_ref.response_status.lock();
            let b = ctx_ref.response_body.lock().clone();
            
            (s, b)
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
            eprintln!("❌ fork() failed");
            process::exit(1);
        }

        if pid == 0 {
            let domain = Domain::IPV4;
            let socket = Socket::new(domain, Type::STREAM, Some(Protocol::TCP)).unwrap();
            
            let _ = socket.set_reuse_address(true);
            let _ = socket.set_reuse_port(true);
            let _ = socket.set_nodelay(true);
            let _ = socket.set_recv_buffer_size(64 * 1024);
            let _ = socket.set_send_buffer_size(64 * 1024);

            let address = format!("{}:{}", host, port).parse::<std::net::SocketAddr>().unwrap();
            socket.bind(&address.into()).unwrap();
            socket.listen(65535).unwrap();

            let listener: TcpListener = socket.into();

            // Fixed: with_gil -> attach
            Python::attach(|py| {
                let sys = py.import("sys").unwrap();
                let path = sys.getattr("path").unwrap();
                let _ = path.call_method1("append", (".",));
                let _ = PyModule::import(py, "handlers"); 

                // Fixed: allow_threads -> detach
                Python::detach(py, || {
                    let rt = Runtime::new().unwrap();
                    rt.block_on(async move {
                        HttpServer::new(|| {
                            App::new()
                                .default_service(web::to(handler))
                        })
                        .listen(listener).unwrap()
                        .workers(1) 
                        .backlog(65535)
                        .keep_alive(KeepAlive::Os)
                        .max_connections(250_000)
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
// Fixed: unused variable `py` -> `_py`
fn run_server(_py: Python<'_>, host: String, port: u16, workers: usize) -> PyResult<()> {
    // Ignore SIGCHLD to prevent zombie processes
    unsafe { libc::signal(libc::SIGCHLD, libc::SIG_IGN); }

    println!("🔥 TurboX V4 Final (Thread-Safe Lazy Context)");
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
