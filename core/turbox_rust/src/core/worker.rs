use pyo3::prelude::*;
use pyo3::ffi;
use pyo3::types::{PyString, PyBool, PyBytes, PyDict, PyModule};
use std::ptr;
use std::cell::RefCell;
use std::ffi::CString;
use std::collections::HashMap;
use pythonize::depythonize;
use serde_json::Value;
use bytes::Bytes;

use crate::core::route::RouteKey;
use crate::core::utils::inject_into_module;

thread_local! {
    static WORKER_INTERPRETER_STATE: RefCell<*mut ffi::PyThreadState> = RefCell::new(ptr::null_mut());
    static FUNCTION_CACHE: RefCell<HashMap<RouteKey, Py<PyAny>>> = RefCell::new(HashMap::new());
}

fn process_body(obj: &Bound<'_, PyAny>) -> Bytes {
  
    if let Ok(s) = obj.cast::<PyString>() {
        if let Ok(bytes) = s.to_str() {
            return Bytes::copy_from_slice(bytes.as_bytes());
        }
        return Bytes::copy_from_slice(s.to_string_lossy().as_bytes());
    }
    
    if let Ok(b) = obj.cast::<PyBool>() {
        return if b.is_true() { Bytes::from_static(b"true") } else { Bytes::from_static(b"false") };
    }

    if let Ok(b) = obj.cast::<PyBytes>() {
        return Bytes::copy_from_slice(b.as_bytes());
    }

    match depythonize::<Value>(obj) {
        Ok(v) => Bytes::from(serde_json::to_vec(&v).unwrap_or_default()),
        Err(_) => {
            let s = obj.str().unwrap_or_else(|_| obj.repr().unwrap());
            Bytes::copy_from_slice(s.to_string_lossy().as_bytes())
        },
    }

}

pub fn ensure_sub_interpreter_initialized() {

    WORKER_INTERPRETER_STATE.with(|cell| {

        let tstate = *cell.borrow();

        if tstate.is_null() {

            unsafe {

                let config = ffi::PyInterpreterConfig {
                    use_main_obmalloc: 0,
                    allow_fork: 0,
                    allow_exec: 0,
                    allow_threads: 1,
                    allow_daemon_threads: 0,
                    check_multi_interp_extensions: 1,
                    gil: ffi::PyInterpreterConfig_OWN_GIL,
                };

                let mut new_interp: *mut ffi::PyThreadState = ptr::null_mut();
                let _ = ffi::Py_NewInterpreterFromConfig(&mut new_interp, &config);
                let py = Python::assume_attached();

                if let Ok(sys) = py.import("sys") {
                    if let Ok(path) = sys.getattr("path") {
                        if let Ok(cwd) = std::env::current_dir() {
                            let _ = path.call_method1("insert", (0, cwd.to_string_lossy()));
                        }
                    }
                }

                let mock_script = r#"
import sys, types
if 'turbox' not in sys.modules:
    m = types.ModuleType('turbox')
    m.Route = type('Route', (), {'add': lambda *args, **kwargs: None})
    m.Server = type('Server', (), {'bind': lambda *args: None, 'workers': lambda *args: None, 'config': lambda *args: None, 'run': lambda *args: None})
    sys.modules['turbox'] = m
    sys.modules['turbox.turbox'] = m
"#;
                let c_script = CString::new(mock_script).expect("Failed to create CString");

                if let Err(e) = py.run(&c_script, None, None) {
                    e.print(py);
                }

                if let Ok(m) = py.import("turbox") {
                    if let Err(e) = inject_into_module(py, &m) {
                        e.print(py);
                    }
                }

                let suspended = ffi::PyEval_SaveThread();
                *cell.borrow_mut() = suspended;

            }

        }

    });

}
