use once_cell::sync::OnceCell;
use pyo3::prelude::*;
use concurrent_queue::ConcurrentQueue;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicI64, Ordering};
use std::thread;

#[derive(Debug)]
struct Job {
    handler: Py<PyAny>,
    arg: i64,
    result: Arc<AtomicI64>,
}

static QUEUE: OnceCell<Arc<ConcurrentQueue<Job>>> = OnceCell::new();
static RUNNING: AtomicBool = AtomicBool::new(true);

fn start_workers(n: usize) {
    let queue = Arc::new(ConcurrentQueue::<Job>::bounded(4096));
    QUEUE.set(queue.clone()).unwrap();

    for _ in 0..n {
        let q = queue.clone();
        thread::spawn(move || {
            // We keep the RUNNING check to prevent the crash
            while RUNNING.load(Ordering::Relaxed) {
                if let Ok(job) = q.pop() {
                    // ---------------------------------------------------
                    // PERFORMANCE NOTE:
                    // We attach to Python only when we have a job.
                    // ---------------------------------------------------
                    Python::attach(|py| {
                        // Use call1 and handle potential errors gracefully 
                        // so a Python exception doesn't kill the Rust thread immediately
                        if let Ok(out) = job.handler.call1(py, (job.arg,)) {
                            if let Ok(val) = out.extract::<i64>(py) {
                                job.result.store(val, Ordering::Release);
                            }
                        }
                    });
                } else {
                    // ---------------------------------------------------
                    // FIX: Back to spin_loop for maximum speed.
                    // This consumes CPU but gives you that ~50us latency.
                    // ---------------------------------------------------
                    std::hint::spin_loop();
                }
            }
        });
    }
}

#[pyfunction]
fn run(py: Python, handler: Py<PyAny>, number: i64) -> PyResult<i64> {
    let result = Arc::new(AtomicI64::new(0));
    let q = QUEUE.get().unwrap();

    // Push the job
    q.push(Job {
        handler,
        arg: number,
        result: result.clone(),
    }).unwrap();

    // Wait for result
    let val = py.detach(move || {
        loop {
            let x = result.load(Ordering::Acquire);
            if x != 0 {
                return x;
            }
            // Check running here too, so the main thread doesn't hang on shutdown
            if !RUNNING.load(Ordering::Relaxed) {
                return -1;
            }
            std::hint::spin_loop();
        }
    });

    Ok(val)
}

#[pyfunction]
fn shutdown() {
    RUNNING.store(false, Ordering::Relaxed);
}

#[pymodule]
fn turbox(_py: Python, m: &Bound<PyModule>) -> PyResult<()> {
    start_workers(8);
    m.add_function(wrap_pyfunction!(run, m)?)?;
    m.add_function(wrap_pyfunction!(shutdown, m)?)?;
    Ok(())
}