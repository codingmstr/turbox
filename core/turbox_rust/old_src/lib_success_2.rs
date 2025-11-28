use once_cell::sync::OnceCell;
use pyo3::prelude::*;
use concurrent_queue::ConcurrentQueue;
use std::sync::Arc;
use std::sync::atomic::{AtomicI64, Ordering};
use std::thread;

#[derive(Debug)]
struct Job {
    handler: Py<PyAny>,
    arg: i64,
    result: Arc<AtomicI64>,
}

static QUEUE: OnceCell<Arc<ConcurrentQueue<Job>>> = OnceCell::new();

fn start_workers(n: usize) {
    let queue = Arc::new(ConcurrentQueue::<Job>::bounded(4096));
    QUEUE.set(queue.clone()).unwrap();

    for _ in 0..n {
        let q = queue.clone();
        thread::spawn(move || {
            loop {
                if let Ok(job) = q.pop() {
                    Python::attach(|py| {
                        let out = job.handler.call1(py, (job.arg,)).unwrap();
                        let val: i64 = out.extract(py).unwrap();
                        job.result.store(val, Ordering::Release);
                    });
                } else {
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

    q.push(Job {
        handler,
        arg: number,
        result: result.clone(),
    }).unwrap();

    let val = py.detach(move || {
        loop {
            let x = result.load(Ordering::Acquire);
            if x != 0 {
                return x;
            }
            std::hint::spin_loop();
        }
    });

    Ok(val)
}

#[pymodule]
fn turbox(_py: Python, m: &Bound<PyModule>) -> PyResult<()> {
    start_workers(8);
    m.add_function(wrap_pyfunction!(run, m)?)?;
    Ok(())
}
