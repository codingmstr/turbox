use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer};
use actix_web::http::KeepAlive;
use bytes::Bytes;
use mimalloc::MiMalloc;
use parking_lot::Mutex;
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

// تخزين الدالة محلياً (Caching)
thread_local! {
    static CACHED_HANDLER: RefCell<Option<Py<PyAny>>> = RefCell::new(None);
}

// =========================================================
//  TurboContext (Lazy & Thread-Safe)
// =========================================================

#[pyclass]
struct TurboContext {
    // البيانات الخام (Rust-owned)
    _path: String,
    _body: Bytes,
    
    // الرد (Thread-Safe Mutability)
    response_status: Mutex<u16>,
    response_body: Mutex<Bytes>,
}

#[pymethods]
impl TurboContext {
    // 1. Lazy Getters: لا نحول البيانات إلا إذا طلبها المستخدم
    #[getter]
    fn path<'py>(&self, py: Python<'py>) -> Bound<'py, PyString> {
        PyString::new(py, &self._path)
    }

    #[getter]
    fn body<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self._body)
    }

    // 2. Responder: يكتب الرد في ذاكرة Rust فوراً
    #[pyo3(signature = (status, body))]
    fn respond(&self, status: u16, body: &Bound<'_, PyAny>) {
        *self.response_status.lock() = status;
        
        let bytes = if let Ok(s) = body.extract::<String>() {
            Bytes::from(s)
        } else if let Ok(b) = body.cast::<PyBytes>() {
            Bytes::copy_from_slice(b.as_bytes())
        } else {
            Bytes::from(body.to_string())
        };
        
        *self.response_body.lock() = bytes;
    }
}

// =========================================================
//  Handler
// =========================================================
async fn handler(req: HttpRequest, body: Bytes) -> HttpResponse {
    let path = req.path();
    
    // نجهز الكائن في Rust (سريع جداً)
    let context_data = TurboContext {
        _path: path.to_string(),
        _body: body,
        response_status: Mutex::new(200), // Default status
        response_body: Mutex::new(Bytes::new()), // Default body
    };

    let (status, resp_bytes) = Python::attach(|py| {
        CACHED_HANDLER.with(|cell| {
            let mut handler_opt = cell.borrow_mut();

            // Lazy Import (مرة واحدة لكل Thread)
            if handler_opt.is_none() {
                let module = PyModule::import(py, "handlers").expect("Failed to import handlers");
                let func = module.getattr("app").expect("Failed to find 'app'");
                *handler_opt = Some(func.into());
            }

            let app_func = handler_opt.as_ref().unwrap();
            
            // إنشاء الكائن وتمريره
            let py_context = Py::new(py, context_data).unwrap();
            
            // استدعاء الدالة
            if let Err(e) = app_func.call1(py, (py_context.clone_ref(py),)) {
                e.print_and_set_sys_last_vars(py);
                return (500, Bytes::from("Internal Python Error"));
            }

            // قراءة الرد من الـ Mutex
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
//  Worker Logic (SO_REUSEPORT + Fork)
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
            
            // Performance Tuning
            let _ = socket.set_reuse_address(true);
            let _ = socket.set_reuse_port(true); // السر هنا
            let _ = socket.set_nodelay(true);
            let _ = socket.set_recv_buffer_size(1024 * 64);
            let _ = socket.set_send_buffer_size(1024 * 64);

            let address = format!("{}:{}", host, port).parse::<std::net::SocketAddr>().unwrap();
            socket.bind(&address.into()).unwrap();
            socket.listen(65535).unwrap();

            let listener: TcpListener = socket.into();

            // تهيئة بايثون مرة واحدة في العملية الجديدة
            Python::attach(|py| {
                let sys = py.import("sys").unwrap();
                let path = sys.getattr("path").unwrap();
                let _ = path.call_method1("append", (".",));
                // Pre-import handlers
                let _ = PyModule::import(py, "handlers"); 

                // تشغيل Actix
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
fn run_server(_py: Python<'_>, host: String, port: u16, workers: usize) -> PyResult<()> {
    unsafe { libc::signal(libc::SIGCHLD, libc::SIG_IGN); }

    println!("🔥 TurboX Classic (Restored Performance) Starting...");
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