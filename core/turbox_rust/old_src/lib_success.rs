use pyo3::prelude::*;
use std::thread;


// pure runner

#[pyfunction]
fn run(py: Python<'_>, handler: Py<PyAny>, number: i64) -> PyResult<i64> {
    let result = handler.call1(py, (number,))?;
    result.extract(py)
}

#[pymodule]
fn turbox(_py: Python, m: &Bound<PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run, m)?)?;
    Ok(())
}


// thread runner

#[pyfunction]
fn run(py: Python<'_>, handler: Py<PyAny>, number: i64) -> PyResult<i64> {

    let py_result = py.detach(move || {

        thread::spawn(move || {
            Python::attach(|py| {
                handler.call1(py, (number,))
            })
        })
        .join()
        .unwrap()

    })?; 

    Python::attach(|py| py_result.extract(py))
}

#[pymodule]
fn turbox(_py: Python, m: &Bound<PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run, m)?)?;
    Ok(())
}
