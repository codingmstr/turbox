use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer};
use tokio::net::UnixStream;
use std::io;
use bytes::BufMut;

const UDS_PATH: &str = "/tmp/actix_python_bridge.sock";
const EMPTY_REQUEST_PAYLOAD: [u8; 0] = [];

async fn uds_proxy_handler(_req: HttpRequest) -> io::Result<HttpResponse> {
    // 1. Prepare minimal request data (Length 0)
    let payload = &EMPTY_REQUEST_PAYLOAD;
    let payload_len = payload.len() as u32;

    // 2. Connect to the Python UDS server
    let mut stream = match UnixStream::connect(UDS_PATH).await {
        Ok(s) => s,
        Err(e) => {
            eprintln!("UDS connection error: {:?}", e);
            return Ok(HttpResponse::InternalServerError().body(format!("Failed to connect to Python: {}", e)));
        }
    };
    
    // 3. Send the request (Length 0)
    let mut buffer = bytes::BytesMut::with_capacity(4);
    buffer.put_u32(payload_len); 

    stream.writable().await?;
    stream.try_write(&buffer)?;
    
    // 4. Receive Response Length (4 bytes)
    let mut len_buffer = [0u8; 4];
    stream.readable().await?;
    if stream.try_read(&mut len_buffer)? == 0 {
        return Ok(HttpResponse::InternalServerError().body("Python closed connection unexpectedly (length read)."));
    }
    let response_len = u32::from_be_bytes(len_buffer);

    // 5. Read the actual response payload
    let mut response_payload = vec![0u8; response_len as usize];
    let mut bytes_read = 0;
    while bytes_read < response_len as usize {
        stream.readable().await?;
        match stream.try_read(&mut response_payload[bytes_read..]) {
            Ok(0) => {
                return Ok(HttpResponse::InternalServerError().body("Python closed connection unexpectedly (payload read)."));
            }
            Ok(n) => {
                bytes_read += n;
            }
            Err(ref e) if e.kind() == io::ErrorKind::WouldBlock => {
                continue;
            }
            Err(e) => {
                return Err(e);
            }
        }
    }

    // 6. Return the raw string response
    let response_string = String::from_utf8(response_payload).unwrap_or_else(|_| "Error decoding response".to_string());
    
    Ok(HttpResponse::Ok().content_type("text/plain").body(response_string))
}

#[actix_web::main]
async fn main() -> io::Result<()> {
    println!("Actix-web server running at http://127.0.0.1:8080");

    HttpServer::new(|| {
        App::new()
            .default_service(web::to(uds_proxy_handler))
            .route("/{path:.*}", web::get().to(uds_proxy_handler))
    })
    .bind(("127.0.0.1", 8080))?
    .workers(32)
    .run()
    .await
}
