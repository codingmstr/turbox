use once_cell::sync::OnceCell;
use pyo3::prelude::*;
use std::sync::mpsc::{self, Sender, Receiver};
use std::thread;

struct Job {
    handler: Py<PyAny>,
    arg: i64,
    reply_tx: mpsc::Sender<i64>,
}

static WORKERS: OnceCell<Vec<Sender<Job>>> = OnceCell::new();

fn start_python_workers(count: usize) {

    let mut senders = Vec::with_capacity(count);

    for _ in 0..count {

        let (tx, rx): (Sender<Job>, Receiver<Job>) = mpsc::channel();
        senders.push(tx);

        thread::spawn(move || {
            
            loop {
              
                let job = rx.recv().unwrap();

                Python::attach(|py| {
                   
                    let result = job.handler.call1(py, (job.arg,)).unwrap();
                    let extracted: i64 = result.extract(py).unwrap();
                    job.reply_tx.send(extracted).unwrap();

                });

            }

        });

    }

    WORKERS.set(senders).expect("Workers already started");

}

#[pyfunction]
fn run(py: Python, handler: Py<PyAny>, number: i64) -> PyResult<i64> {
   
    let (reply_tx, reply_rx) = mpsc::channel::<i64>();

    let workers = WORKERS.get().expect("Workers not started");
    let idx = number as usize % workers.len();

    workers[idx].send(Job {
        handler,
        arg: number,
        reply_tx,
    }).unwrap();

    let result = py.detach(move || reply_rx.recv().unwrap());
    Ok(result)

}

#[pymodule]
fn turbox(_py: Python, m: &Bound<PyModule>) -> PyResult<()> {

    start_python_workers(8); // 8 threads

    m.add_function(wrap_pyfunction!(run, m)?)?;
    Ok(())

}
