import Foundation
import Network

public struct HTTPRequest: Sendable {
    public let method: String
    public let path: String
    public let headers: [String: String]
    public let body: Data
}

public struct HTTPResponse: Sendable {
    public let status: Int
    public let contentType: String
    public let body: Data
    public let headers: [String: String]

    public init(status: Int = 200, contentType: String = "application/octet-stream", body: Data = Data(), headers: [String: String] = [:]) {
        self.status = status
        self.contentType = contentType
        self.body = body
        self.headers = headers
    }
}

public final class LoopbackHTTPServer: @unchecked Sendable {
    public typealias Handler = @Sendable (HTTPRequest) -> HTTPResponse
    private let queue = DispatchQueue(label: "com.linzecolin.harnessui.http")
    private var listener: NWListener?

    public init() {}

    public func start(port: UInt16, handler: @escaping Handler) throws {
        let parameters = NWParameters.tcp
        guard let endpointPort = NWEndpoint.Port(rawValue: port) else { throw NSError(domain: "HarnessUI", code: 1) }
        parameters.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: endpointPort)
        let listener = try NWListener(using: parameters)
        listener.newConnectionHandler = { [weak self] connection in self?.accept(connection, handler: handler) }
        listener.start(queue: queue)
        self.listener = listener
    }

    public func stop() {
        listener?.cancel()
        listener = nil
    }

    private func accept(_ connection: NWConnection, handler: @escaping Handler) {
        connection.start(queue: queue)
        receive(connection, accumulated: Data(), handler: handler)
    }

    private func receive(_ connection: NWConnection, accumulated: Data, handler: @escaping Handler) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) { [weak self] data, _, complete, error in
            guard let self else { return }
            var combined = accumulated
            if let data { combined.append(data) }
            if let request = self.parse(combined) {
                self.send(self.response(for: request, handler: handler), on: connection)
            } else if error == nil && !complete && combined.count < 2 * 1024 * 1024 {
                self.receive(connection, accumulated: combined, handler: handler)
            } else {
                connection.cancel()
            }
        }
    }

    private func response(for request: HTTPRequest, handler: Handler) -> HTTPResponse {
        guard trustedHost(request.headers["host"] ?? "") else { return HTTPResponse(status: 400) }
        let origin = request.headers["origin"]
        if let origin, !trustedOrigin(origin) { return HTTPResponse(status: 403) }
        let response = handler(request)
        var headers = response.headers
        headers["Vary"] = "Origin"
        headers["X-Content-Type-Options"] = "nosniff"
        if let origin { headers["Access-Control-Allow-Origin"] = origin }
        return HTTPResponse(status: response.status, contentType: response.contentType, body: response.body, headers: headers)
    }

    private func trustedHost(_ raw: String) -> Bool {
        let value = raw.lowercased()
        return value == "localhost" || value.hasPrefix("localhost:") ||
            value == "127.0.0.1" || value.hasPrefix("127.0.0.1:") ||
            value == "[::1]" || value.hasPrefix("[::1]:")
    }

    private func trustedOrigin(_ raw: String) -> Bool {
        if raw == "null" { return true }
        guard let value = URLComponents(string: raw), value.scheme == "http", let host = value.host?.lowercased() else { return false }
        return host == "localhost" || host == "127.0.0.1" || host == "::1"
    }

    private func parse(_ data: Data) -> HTTPRequest? {
        guard let marker = "\r\n\r\n".data(using: .utf8), let range = data.range(of: marker),
              let head = String(data: data[..<range.lowerBound], encoding: .utf8) else { return nil }
        let lines = head.components(separatedBy: "\r\n")
        guard let first = lines.first else { return nil }
        let parts = first.split(separator: " ", maxSplits: 2).map(String.init)
        guard parts.count >= 2 else { return nil }
        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            let pair = line.split(separator: ":", maxSplits: 1).map(String.init)
            if pair.count == 2 { headers[pair[0].lowercased()] = pair[1].trimmingCharacters(in: .whitespaces) }
        }
        let length = Int(headers["content-length"] ?? "0") ?? 0
        let bodyStart = range.upperBound
        guard data.count >= bodyStart + length else { return nil }
        let body = Data(data[bodyStart..<(bodyStart + length)])
        let requestPath = parts[1].split(separator: "?", maxSplits: 1).first.map(String.init) ?? "/"
        return HTTPRequest(method: parts[0], path: requestPath, headers: headers, body: body)
    }

    private func send(_ response: HTTPResponse, on connection: NWConnection) {
        let phrases = [200: "OK", 202: "Accepted", 204: "No Content", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 500: "Internal Server Error"]
        var headers = response.headers
        headers["Content-Type"] = response.contentType
        headers["Content-Length"] = String(response.body.count)
        headers["Connection"] = "close"
        let fields = headers.sorted { $0.key < $1.key }.map { "\($0.key): \($0.value)" }.joined(separator: "\r\n")
        let head = "HTTP/1.1 \(response.status) \(phrases[response.status] ?? "Response")\r\n\(fields)\r\n\r\n"
        var payload = Data(head.utf8)
        payload.append(response.body)
        connection.send(content: payload, completion: .contentProcessed { _ in connection.cancel() })
    }
}
