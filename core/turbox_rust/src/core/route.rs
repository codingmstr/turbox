use pyo3::prelude::*;
use dashmap::DashMap;
use lazy_static::lazy_static;
use std::path::{Path, Component};

#[derive(Clone, Hash, PartialEq, Eq, Debug)]
pub struct RouteKey {
    pub module: String,
    pub handler: String,
}

lazy_static! {
    pub static ref ROUTES: DashMap<(String, String), RouteKey> = DashMap::new();
}

#[pyclass]
#[derive(Clone)]
pub struct Route {}

#[pymethods]
impl Route {

    #[new]
    pub fn new() -> Self {
        Route {}
    }
    pub fn add(&self, method: String, path: String, handler: Bound<'_, PyAny>) -> PyResult<()> {
        register_route_logic(method, path, handler)
    }

}

fn register_route_logic( method: String, path: String, handler: Bound<'_, PyAny> ) -> PyResult<()> {

    let func_name: String = handler.getattr("__name__")?.extract()?;
    let mut mod_name: String = handler.getattr("__module__")?.extract()?;

    if mod_name == "__main__" {
        if let Ok(globals) = handler.getattr("__globals__") {
            if let Ok(file_path_item) = globals.get_item("__file__") {
                let file_path: String = file_path_item.extract()?;
                let path_obj = Path::new(&file_path);
                
                if let Ok(cwd) = std::env::current_dir() {
                    if let Ok(relative) = path_obj.strip_prefix(&cwd) {
                        let mut components: Vec<String> = Vec::new();
                        
                        for component in relative.components() {
                            if let Component::Normal(s) = component {
                                components.push(s.to_string_lossy().to_string());
                            }
                        }

                        if let Some(last) = components.last_mut() {
                            if let Some(stem) = Path::new(last).file_stem() {
                                *last = stem.to_string_lossy().to_string();
                            }
                        }

                        if components.last().map(|s| s.as_str()) == Some("__init__") {
                            components.pop();
                        }

                        if !components.is_empty() {
                            mod_name = components.join(".");
                        }
                    } else {
                        if let Some(stem) = path_obj.file_stem() {
                            mod_name = stem.to_string_lossy().to_string();
                        }
                    }
                }
            }
        }
    }

    ROUTES.insert((method, path), RouteKey { module: mod_name, handler: func_name });
    Ok(())

}
