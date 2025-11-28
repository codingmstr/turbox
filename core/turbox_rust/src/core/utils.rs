use pyo3::prelude::*;
use pyo3::types::PyModule;
use inventory;

pub struct RegistryEntry(pub fn(Python<'_>, &Bound<'_, PyModule>) -> PyResult<()>);
inventory::collect!(RegistryEntry);

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
            $crate::core::utils::RegistryEntry(|py, m| {
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
      
        $(#[$meta])*
        pub struct $name $($rest)*

        inventory::submit! {
            $crate::core::utils::RegistryEntry(|py, m| {
                let type_obj = py.get_type::<$name>();
                m.setattr(stringify!($name), type_obj)?;
                Ok(())
            })
        }

    };

}
