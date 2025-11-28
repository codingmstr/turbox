use std::cell::RefCell;
use std::collections::HashMap;
use std::convert::Infallible;
use std::ptr;
use std::thread;

use bytes::Bytes;
use dashmap::DashMap;
use http_body_util::{BodyExt, Full};
use hyper::body::Incoming;
use hyper::header::CONTENT_TYPE;
use hyper::server::conn::http1;
use hyper::service::service_fn;
use hyper::{Request, Response, StatusCode};
use hyper_util::rt::TokioIo;
use lazy_static::lazy_static;
// 🛑 System Allocator is more stable for OWN_GIL mixed workloads preventing hiccups
// use mimalloc::MiMalloc; 
use pyo3::ffi;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyString};
use tokio::net::TcpListener;
use tokio::runtime::Builder;
use tokio::task::LocalSet;
use pythonize::depythonize;
use serde_json::Value;

#[derive(Clone, Hash, PartialEq, Eq, Debug)]
struct RouteKey {
    module: String,
    handler: String,
}

lazy_static! {
    static ref ROUTES: DashMap<(String, String), RouteKey> = DashMap::new();
}

struct CachedPyKeys {
    method: Py<PyString>,
    path: Py<PyString>,
    headers: Py<PyString>,
    body: Py<PyString>,
}

thread_local! {
    static WORKER_INTERPRETER_STATE: RefCell<*mut ffi::PyThreadState> = RefCell::new(ptr::null_mut());
    
    // 🚀 L1 CACHE: Local Fast Route Lookup (Avoids DashMap Locks)
    // Key: (Method, Path) -> Value: Python Handler
    static FAST_ROUTE_CACHE: RefCell<HashMap<(String, String), Py<PyAny>>> = RefCell::new(HashMap::new());
    
    // Keys Cache
    static PY_KEYS_CACHE: RefCell<Option<CachedPyKeys>> = RefCell::new(None);
}

fn init_worker_interpreter() {
    WORKER_INTERPRETER_STATE.with(|cell| {
        let tstate = *cell.borrow();
        if tstate.is_null() {
            unsafe {
                let _gstate = ffi::PyGILState_Ensure();

                let config = ffi::PyInterpreterConfig {
                    use_main_obmalloc: 0, // Isolated Heaps (Best Performance)
                    allow_fork: 0,
                    allow_exec: 0,
                    allow_threads: 1,
                    allow_daemon_threads: 0,
                    check_multi_interp_extensions: 1, 
                    gil: ffi::PyInterpreterConfig_OWN_GIL, // True Parallelism
                };
                
                let mut new_interp: *mut ffi::PyThreadState = ptr::null_mut();
                let _ = ffi::Py_NewInterpreterFromConfig(&mut new_interp, &config);
                
                if !new_interp.is_null() {
                    let py = Python::assume_attached();
                    
                    // 1. Inject sys.path
                    if let Ok(sys) = py.import("sys") {
                        if let Ok(path) = sys.getattr("path") {
                            if let Ok(cwd) = std::env::current_dir() {
                                 let _ = path.call_method1("insert", (0, cwd.to_string_lossy()));
                            }
                        }
                    }

                    // 2. 🔥 DISABLE GC (Huge Performance Boost for Benchmarks)
                    // In a stateless web server, RefCounting is usually enough.
                    // Periodic GC pauses kill the 99th percentile latency and throughput.
                    if let Ok(gc) = py.import("gc") {
                        let _ = gc.call_method0("disable");
                    }

                    // 3. Pre-allocate Keys
                    PY_KEYS_CACHE.with(|keys_cell| {
                        *keys_cell.borrow_mut() = Some(CachedPyKeys {
                            method: PyString::new(py, "method").into(),
                            path: PyString::new(py, "path").into(),
                            headers: PyString::new(py, "headers").into(),
                            body: PyString::new(py, "body").into(),
                        });
                    });

                    let suspended = ffi::PyEval_SaveThread();
                    *cell.borrow_mut() = suspended;
                } else {
                    ffi::PyErr_Print();
                    panic!("CRITICAL: Failed to initialize sub-interpreter.");
                }
            }
        }
    });
}

fn process_python_result(obj: Bound<'_, PyAny>) -> (Bytes, &'static str) {
    // Most likely response in benchmarks is JSON or Plain Text
    
    // Check String
    if obj.is_instance_of::<PyString>() {
        let s: String = obj.extract().unwrap_or_default();
        return (Bytes::from(s), "text/plain; charset=utf-8");
    }

    // Check Bytes
    if obj.is_instance_of::<PyBytes>() {
        let b: &[u8] = obj.extract().unwrap_or_default();
        return (Bytes::copy_from_slice(b), "application/octet-stream");
    }

    // Check Bool
    if obj.is_instance_of::<PyBool>() {
        let b: bool = obj.extract().unwrap_or(false);
        let bytes = if b { Bytes::from_static(b"true") } else { Bytes::from_static(b"false") };
        return (bytes, "application/json");
    }

    // Fallback to JSON (Pythonize)
    match depythonize::<Value>(&obj) {
        Ok(v) => {
            let bytes = serde_json::to_vec(&v).unwrap_or_default();
            (Bytes::from(bytes), "application/json")
        },
        Err(_) => {
            let s = obj.to_string();
            (Bytes::from(s), "text/plain")
        }
    }
}

async fn turbo_handler(
    req: Request<Incoming>,
) -> Result<Response<Full<Bytes>>, Infallible> {
    
    let (parts, body_stream) = req.into_parts();
    
    // Optimistic: Most benchmark URLs are short and ascii.
    let method_str = parts.method.to_string();
    let path_str = parts.uri.path().to_string();

    // 🚀 L1 CACHE LOOKUP (Avoid DashMap if possible)
    // We can't access thread_local here easily without entering the thread context later.
    // So we just pass the strings and do lookup inside the WORKER_INTERPRETER_STATE block
    // to keep the "unsafe" block contiguous and efficient.

    let raw_body_bytes = match body_stream.collect().await {
        Ok(collected) => collected.to_bytes(),
        Err(_) => return Ok(Response::builder().status(500).body(Full::new(Bytes::from("Body Error"))).unwrap()),
    };

    WORKER_INTERPRETER_STATE.with(|cell| {
        unsafe {
            let suspended = *cell.borrow();
            ffi::PyEval_RestoreThread(suspended);
            let py = Python::assume_attached();

            // 🔥 FAST ROUTE LOOKUP (L1 Cache)
            let func_result: Option<Py<PyAny>> = FAST_ROUTE_CACHE.with(|local_cache_cell| {
                let mut local_cache = local_cache_cell.borrow_mut();
                
                // 1. Check L1 Local Cache
                if let Some(f) = local_cache.get(&(method_str.clone(), path_str.clone())) {
                    Some(f.clone_ref(py))
                } else {
                    // 2. Fallback to L2 Global DashMap
                    if let Some(entry) = ROUTES.get(&(method_str.clone(), path_str.clone())) {
                        let cfg = entry.value();
                        match PyModule::import(py, &*cfg.module) {
                            Ok(m) => match m.getattr(&*cfg.handler) {
                                Ok(f) => {
                                    let f_owned = f.unbind();
                                    // 3. Promote to L1 Cache
                                    local_cache.insert((method_str.clone(), path_str.clone()), f_owned.clone_ref(py));
                                    Some(f_owned)
                                },
                                Err(_) => None,
                            },
                            Err(_) => None,
                        }
                    } else {
                        None
                    }
                }
            });

            let response = if let Some(func) = func_result {
                
                let ctx = PyDict::new(py);
                
                // 🔥 INTERNED KEYS ACCESS
                PY_KEYS_CACHE.with(|keys_cache| {
                    if let Some(keys) = keys_cache.borrow().as_ref() {
                        let _ = ctx.set_item(keys.method.bind(py), &method_str);
                        let _ = ctx.set_item(keys.path.bind(py), &path_str);
                        
                        // PyBytes Body
                        let py_body = PyBytes::new(py, &raw_body_bytes);
                        let _ = ctx.set_item(keys.body.bind(py), py_body);

                        let headers_dict = PyDict::new(py);
                        for (k, v) in parts.headers.iter() {
                                let val = v.to_str().unwrap_or(""); 
                                let _ = headers_dict.set_item(k.as_str(), val);
                        }
                        let _ = ctx.set_item(keys.headers.bind(py), headers_dict);
                    }
                });

                match func.call1(py, (ctx,)) {
                    Ok(res) => {
                        let (body, content_type) = process_python_result(res.into_bound(py));
                        Ok(Response::builder()
                            .header(CONTENT_TYPE, content_type)
                            .body(Full::new(body))
                            .unwrap())
                    },
                    Err(e) => {
                        e.print(py);
                        Ok(Response::builder().status(500).body(Full::new(Bytes::from("Python Exception"))).unwrap())
                    }
                }
            } else {
                Ok(Response::builder().status(500).body(Full::new(Bytes::from("Handler Not Found"))).unwrap())
            };

            let new_suspended = ffi::PyEval_SaveThread();
            *cell.borrow_mut() = new_suspended;

            response
        }
    })
}

#[pyfunction]
fn add_route(_py: Python, method: String, path: String, handler: Bound<'_, PyAny>) -> PyResult<()> {
    let func_name: String = handler.getattr("__name__")?.extract()?;
    let mod_name: String = handler.getattr("__module__")?.extract()?;
    ROUTES.insert((method, path), RouteKey { module: mod_name, handler: func_name });
    Ok(())
}

#[pyfunction]
fn run_server(py: Python, host: String, port: u16, workers: usize) -> PyResult<()> {
    let addr_str = format!("{}:{}", host, port);
    println!("🚀 TurboX Hyper-Core v1.8.1 (SPEED DEMON).");
    println!("💎 OPTIMIZATION: L1 Local Cache + No GC + Interning.");
    println!("⚡ ARCH: Thread-per-Core + LocalSet + OWN_GIL.");
    println!("🎧 Listening on http://{}", addr_str);

    let std_listener = std::net::TcpListener::bind(addr_str).unwrap();
    std_listener.set_nonblocking(true).unwrap(); 
    
    py.detach(move || {
        let mut handles = Vec::with_capacity(workers);

        for _i in 0..workers {
            let listener_clone = std_listener.try_clone().unwrap();
            
            let handle = thread::spawn(move || {
                let rt = Builder::new_current_thread()
                    .enable_all()
                    .build()
                    .unwrap();

                let local = LocalSet::new();

                local.block_on(&rt, async move {
                    init_worker_interpreter();
                    
                    let listener = TcpListener::from_std(listener_clone).unwrap();
                    
                    loop {
                        let (stream, _) = match listener.accept().await {
                            Ok(s) => s,
                            Err(_) => continue,
                        };

                        let io = TokioIo::new(stream);

                        tokio::task::spawn_local(async move {
                            if let Err(_err) = http1::Builder::new()
                                .serve_connection(io, service_fn(turbo_handler))
                                .await
                            {
                                // Error handling
                            }
                        });
                    }
                });
            });
            handles.push(handle);
        }

        for h in handles {
            h.join().unwrap();
        }
    });

    Ok(())
}

#[pymodule]
fn turbox(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(add_route, m)?)?;
    m.add_function(wrap_pyfunction!(run_server, m)?)?;
    Ok(())
}
