use pyo3::prelude::*;
use pyo3::types::{PyModule};
use std::sync::{Arc, OnceLock};
use std::net::SocketAddr;
use std::thread;
use tokio::sync::oneshot;
use actix_web::{web, App, HttpServer, HttpResponse, HttpRequest, Responder};
use actix_web::http::header::HeaderMap;
use socket2::{Socket, Domain, Type, Protocol};
use parking_lot::Mutex;
use std::process;

static WORKER_LOOP: OnceLock<Py<PyAny>> = OnceLock::new();

fn init_python_loop(py: Python) -> PyResult<()> {
    let asyncio = PyModule::import(py, "asyncio")?;
    let loop_obj = asyncio.call_method0("new_event_loop")?;
    asyncio.call_method1("set_event_loop", (&loop_obj,))?;
    
    let loop_ref = loop_obj.clone().unbind();
    WORKER_LOOP.set(loop_ref).map_err(|_| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Loop set"))?;
    
    let loop_for_thread = loop_obj.clone().unbind();
    thread::spawn(move || {
        Python::attach(|py| {
            let loop_bound = loop_for_thread.bind(py);
            let _ = loop_bound.call_method0("run_forever");
        });
    });
    Ok(())
}

#[pyclass]
struct RsgiHeaders {
    inner: Arc<HeaderMap>,
}

#[pymethods]
impl RsgiHeaders {
    
    fn __getitem__(&self, key: &str) -> PyResult<String> {
        if let Some(val) = self.inner.get(key) {
            return Ok(String::from_utf8_lossy(val.as_bytes()).to_string());
        }
        Err(pyo3::exceptions::PyKeyError::new_err(key.to_owned()))
    }

    fn __contains__(&self, key: &str) -> bool {
        self.inner.contains_key(key)
    }

    fn get(&self, key: &str, default: Option<String>) -> Option<String> {
        if let Some(val) = self.inner.get(key) {
            return Some(String::from_utf8_lossy(val.as_bytes()).to_string());
        }
        default
    }

    fn keys(&self) -> Vec<String> {
        self.inner.keys().map(|k| k.as_str().to_string()).collect()
    }
    
}

enum RsgiResponse {
    Body { status: u16, headers: Vec<(String, String)>, body: Vec<u8> },
}

#[pyclass]
struct RsgiProtocol {
    tx: Mutex<Option<oneshot::Sender<RsgiResponse>>>,
}

#[pymethods]
impl RsgiProtocol {
    #[pyo3(signature = (status=200, headers=vec![], body=Vec::new()))]
    fn response_bytes(&self, status: u16, headers: Vec<(String, String)>, body: Vec<u8>) {
        if let Some(tx) = self.tx.lock().take() {
            let _ = tx.send(RsgiResponse::Body { status, headers, body });
        }
    }

    #[pyo3(signature = (status=200, headers=vec![], body=String::new()))]
    fn response_str(&self, status: u16, headers: Vec<(String, String)>, body: String) {
        self.response_bytes(status, headers, body.into_bytes())
    }
}

#[pyclass]
struct RsgiScope {
    inner_proto: String,
    inner_http_version: String,
    inner_scheme: String,
    inner_method: String,
    inner_path: String,
    inner_query_string: String,
    headers_wrapper: Py<RsgiHeaders>, 
    client_ip: String,
    client_port: u16,
}

#[pymethods]
impl RsgiScope {
    #[getter]
    fn proto(&self) -> &str { &self.inner_proto }
    #[getter]
    fn http_version(&self) -> &str { &self.inner_http_version }
    #[getter]
    fn scheme(&self) -> &str { &self.inner_scheme }
    #[getter]
    fn method(&self) -> &str { &self.inner_method }
    #[getter]
    fn path(&self) -> &str { &self.inner_path }
    #[getter]
    fn query_string(&self) -> &str { &self.inner_query_string }
    #[getter]
    fn client(&self) -> (String, u16) { (self.client_ip.clone(), self.client_port) }
    #[getter]
    fn server(&self) -> (&str, u16) { ("127.0.0.1", 8080) }

    #[getter]
    fn headers<'p>(&self, py: Python<'p>) -> PyResult<Bound<'p, RsgiHeaders>> {
        Ok(self.headers_wrapper.bind(py).clone())
    }
}

async fn rust_handler(
    req: HttpRequest, 
    py_handler: web::Data<Arc<Py<PyAny>>>
) -> impl Responder {
    
    let (tx, rx) = oneshot::channel::<RsgiResponse>();

    let method = req.method().to_string();
    let path = req.path().to_string();
    let query = req.query_string().to_string();
    let headers_arc = Arc::new(req.headers().clone());

    let (client_ip, client_port) = if let Some(addr) = req.peer_addr() {
        (addr.ip().to_string(), addr.port())
    } else {
        ("0.0.0.0".to_string(), 0)
    };

    let handler_ref = py_handler.get_ref().clone();

    Python::attach(|py| {
        if let Some(loop_py) = WORKER_LOOP.get() {
            
            let rsgi_headers = RsgiHeaders { inner: headers_arc };
            let py_headers = Py::new(py, rsgi_headers).unwrap();

            let scope = RsgiScope {
                inner_proto: "http".to_string(),
                inner_http_version: "1.1".to_string(),
                inner_scheme: "http".to_string(),
                inner_method: method,
                inner_path: path,
                inner_query_string: query,
                headers_wrapper: py_headers,
                client_ip,
                client_port,
            };

            let protocol = RsgiProtocol { tx: Mutex::new(Some(tx)) };
            let app = handler_ref.bind(py);
            
            if let (Ok(py_scope), Ok(py_proto)) = (Py::new(py, scope), Py::new(py, protocol)) {
                match app.call1((py_scope, py_proto)) {
                    Ok(coroutine) => {
                        if let Ok(asyncio) = PyModule::import(py, "asyncio") {
                            let loop_bound = loop_py.bind(py);
                            let _ = asyncio.call_method1("run_coroutine_threadsafe", (coroutine, loop_bound));
                        }
                    },
                    Err(e) => e.print(py),
                }
            }
        }
    });

    match rx.await {
        Ok(RsgiResponse::Body { status, headers, body }) => {
            let mut builder = HttpResponse::build(actix_web::http::StatusCode::from_u16(status).unwrap());
            for (k, v) in headers {
                builder.insert_header((k, v));
            }
            builder.body(body)
        },
        Err(_) => HttpResponse::InternalServerError().body("Timeout"),
    }
}

fn create_listening_socket(addr: SocketAddr) -> std::net::TcpListener {
    let domain = Domain::for_address(addr);
    let socket = Socket::new(domain, Type::STREAM, Some(Protocol::TCP)).unwrap();
    #[cfg(unix)]
    {
        let _ = socket.set_reuse_port(true);
    }
    socket.set_reuse_address(true).unwrap();
    
    if let Err(e) = socket.set_nodelay(true) {
        eprintln!("Failed to set TCP_NODELAY: {}", e);
    }

    socket.bind(&addr.into()).unwrap();
    socket.listen(8192).unwrap(); 
    socket.into()
}

#[tokio::main]
async fn run_worker_actix(_worker_id: i32, handler: Py<PyAny>) {
    Python::attach(|py| {
        let _ = init_python_loop(py);
    });

    let shared_handler = Arc::new(handler);
    let addr: SocketAddr = "0.0.0.0:8080".parse().unwrap();
    let listener = create_listening_socket(addr);

    let server = HttpServer::new(move || {
        App::new()
            .app_data(web::Data::new(shared_handler.clone()))
            .default_service(web::to(rust_handler))
    })
    .listen(listener).unwrap()
    .workers(1)
    .backlog(8192)
    .max_connections(200_000)
    .run();

    let _ = server.await;
}

#[pyfunction]
fn serve(py: Python, handler: Py<PyAny>, workers: usize) -> PyResult<()> {
    let os = PyModule::import(py, "os")?;
    let mut children = Vec::new();

    println!("👑 TurboX Ultimate (Granian-Like Headers): Master {} with {} workers", std::process::id(), workers);

    for i in 0..workers {
        let worker_handler = handler.clone_ref(py);
        let pid_obj = os.call_method0("fork")?;
        let pid: i32 = pid_obj.extract()?;

        if pid == 0 {
            Python::attach(|py| {
                py.detach(|| {
                    run_worker_actix(i as i32, worker_handler);
                });
            });
            process::exit(0);
        } else {
            children.push(pid);
        }
    }
    
    for pid in children {
        unsafe {
            let mut status = 0;
            libc::waitpid(pid, &mut status, 0);
        }
    }
    Ok(())
}

#[pymodule]
fn turbox(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(serve, m)?)?;
    Ok(())
}
