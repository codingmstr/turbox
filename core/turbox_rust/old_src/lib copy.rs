use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer};
use actix_web::http::KeepAlive;
use bytes::Bytes;
use pyo3::prelude::*;
use pyo3::types::PyModule;

use std::os::fd::AsRawFd;
use std::os::unix::io::FromRawFd;

use std::net::TcpListener;
use std::process;
use std::thread;
use std::time::Duration;

use libc;
use tokio::runtime::Runtime;

// =========================================================
//  TurboX — Simple Actix Handler
// =========================================================
async fn handler(req: HttpRequest, body: String) -> HttpResponse {
    let path = req.path().to_string();

    let output = Python::attach(|py| {
        let module = PyModule::import(py, "handlers").unwrap();
        let func = module.getattr("app").unwrap();
        func.call1((path, body))
            .unwrap()
            .extract::<String>()
            .unwrap()
    });

    HttpResponse::Ok().body(Bytes::from(output))
}

// =========================================================
//  Master Process — Main Supervisor
// =========================================================
fn spawn_worker(listener_fd: i32) {
    unsafe {
        let pid = libc::fork();

        if pid < 0 {
            eprintln!("❌ fork() failed");
            process::exit(1);
        }

        if pid == 0 {
            // =======================
            // CHILD WORKER PROCESS
            // =======================
            let listener = TcpListener::from_raw_fd(listener_fd);

            Python::with_gil(|py| {
                Python::detach(py, || {
                    let rt = Runtime::new().unwrap();
                    rt.block_on(async move {
                        HttpServer::new(|| App::new().default_service(web::to(handler)))
                            .listen(listener)
                            .unwrap()
                            .workers(1)
                            .keep_alive(KeepAlive::Os)
                            .backlog(16384)
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
    // =========================================================
    //  Create listener BEFORE forking
    // =========================================================
    let listener = TcpListener::bind((host.as_str(), port))
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Bind failed: {e}")))?;

    listener
        .set_nonblocking(true)
        .map_err(|_| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Cannot set nonblocking"))?;

    let listener_fd = listener.as_raw_fd();

    // =========================================================
    //  Ignore SIGCHLD → No zombies
    // =========================================================
    unsafe {
        libc::signal(libc::SIGCHLD, libc::SIG_IGN);
    }

    println!("🔥 TurboX Master Engine Starting...");
    println!("   Host: {}:{}", host, port);
    println!("   Workers: {}", workers);

    // =========================================================
    //  Fork Worker Processes
    // =========================================================
    for _ in 0..workers {
        spawn_worker(listener_fd);
    }

    // =========================================================
    //  MASTER LOOP — stays alive forever
    // =========================================================
    loop {
        thread::sleep(Duration::from_secs(1));
        // هنا ممكن نضيف health-check أو restart logic لو عايز
    }

    #[allow(unreachable_code)]
    Ok(())
}

#[pymodule]
fn turbox(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_server, m)?)?;
    Ok(())
}
