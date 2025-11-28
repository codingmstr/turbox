use pyo3::prelude::*;
use inventory;

pub struct RegistryEntry(pub fn(Python<'_>, &Bound<'_, PyModule>) -> PyResult<()>);

pub fn inject_into_module(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    for entry in inventory::iter::<RegistryEntry> {
        (entry.0)(py, m)?;
    }
    Ok(())
}

#[macro_export]
macro_rules! turbox_fn {
    ($(#[$meta:meta])* pub fn $name:ident $($rest:tt)*) => {
        #[pyfunction]
        $(#[$meta])*
        pub fn $name $($rest)*

        inventory::submit! {
            $crate::registry::RegistryEntry(|py, m| {
                // تماماً مثل كودك القديم: wrap_pyfunction ثم setattr
                let func = pyo3::wrap_pyfunction!($name, py)?;
                m.setattr(stringify!($name), func)?;
                Ok(())
            })
        }
    };
}

#[macro_export]
macro_rules! turbox_class {
    ($(#[$meta:meta])* pub struct $name:ident $($rest:tt)*) => {
        #[pyclass]
        $(#[$meta])*
        pub struct $name $($rest)*

        inventory::submit! {
            $crate::registry::RegistryEntry(|py, m| {
                // ✅ FIX: استخدام get_type بدلاً من get_type_bound (تحديث PyO3 0.23+)
                let type_obj = py.get_type::<$name>();
                m.setattr(stringify!($name), type_obj)?;
                Ok(())
            })
        }
    };
}

// --- التعريفات ---

turbox_class! {
    #[derive(Clone)]
    pub struct Response {
        #[pyo3(get, set)]
        pub body: String,
        #[pyo3(get, set)]
        pub status: u16,
        #[pyo3(get, set)]
        pub content_type: String,
    }
}

#[pymethods]
impl Response {
    #[new]
    #[pyo3(signature = (body, status=200, content_type="text/plain".to_string()))]
    fn new(body: String, status: u16, content_type: String) -> Self {
        Response { body, status, content_type }
    }

    fn to_json(&self) -> String {
        format!("{{ \"status\": {}, \"body\": \"{}\" }}", self.status, self.body)
    }
}

turbox_fn! {
    pub fn jsonify(data: String) -> String {
        format!("{{ \"json_wrapper\": {} }}", data)
    }
}
