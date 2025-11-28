use pyo3::prelude::*;

#[pyclass]
#[derive(Clone)]
pub struct Response {
    pub body: String,
    pub status: u16,
    pub content_type: String,
}

#[pymethods]
impl Response {

    #[new]
    #[pyo3(signature = (body, status=200, content_type="text/plain".to_string()))]
    pub fn new(body: String, status: u16, content_type: String) -> Self {
        Response { body, status, content_type }
    }
    fn json(&self) -> String {
        format!("{{ \"status\": {}, \"body\": \"{}\" }}", self.status, self.body)
    }
    fn __repr__(&self) -> String {
        format!("<Response {} len={}>", self.status, self.body.len())
    }

}
