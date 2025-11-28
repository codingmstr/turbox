use pyo3::prelude::*;

#[pyclass]
#[derive(Clone)]
pub struct Request {
    pub method: String,
    pub path: String,
    pub body: String,
}

#[pymethods]
impl Request {
 
    #[new]
    pub fn new(method: String, path: String, body: String) -> Self {
        Request { method, path, body }
    }
    fn json(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let json_mod = py.import("json")?;
        Ok(json_mod.call_method1("loads", (&self.body,))?.unbind())
    }
    fn __repr__(&self) -> String {
        format!("<Request method={} path={}>", self.method, self.path)
    }

}
