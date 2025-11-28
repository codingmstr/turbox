use pyo3::prelude::*;

pub mod core;

use core::route::Route;
use core::server::Server;
use core::request::Request;
use core::response::Response;

#[pymodule]
fn turbox(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
  
    m.add_class::<Route>()?;
    m.add_class::<Server>()?;
    m.add_class::<Request>()?;
    m.add_class::<Response>()?;

    Ok(())

}
