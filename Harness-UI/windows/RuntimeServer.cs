using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace HarnessUI;

internal sealed class RuntimeServer : IAsyncDisposable
{
    private readonly HarnessStore store;
    private readonly string webRoot;
    private WebApplication? application;

    internal RuntimeServer(HarnessStore store, string webRoot)
    {
        this.store = store;
        this.webRoot = webRoot;
    }

    internal async Task StartAsync(ushort port, CancellationToken cancellationToken = default)
    {
        var options = new WebApplicationOptions
        {
            Args = [],
            ApplicationName = typeof(RuntimeServer).Assembly.FullName,
            ContentRootPath = AppContext.BaseDirectory,
        };
        var builder = WebApplication.CreateSlimBuilder(options);
        builder.Logging.ClearProviders();
        builder.WebHost.ConfigureKestrel(server =>
        {
            server.AddServerHeader = false;
            server.Listen(IPAddress.Loopback, port, listen => listen.Protocols = HttpProtocols.Http1);
            server.Limits.MaxRequestBodySize = 1_048_576;
        });
        var app = builder.Build();

        app.Use(async (context, next) =>
        {
            var host = context.Request.Host.Host.ToLowerInvariant();
            if (host is not ("127.0.0.1" or "localhost" or "::1"))
            {
                context.Response.StatusCode = StatusCodes.Status400BadRequest;
                return;
            }
            var origin = context.Request.Headers.Origin.ToString();
            if (!IsTrustedOrigin(origin))
            {
                context.Response.StatusCode = StatusCodes.Status403Forbidden;
                return;
            }
            if (!string.IsNullOrEmpty(origin))
                context.Response.Headers["Access-Control-Allow-Origin"] = origin;
            context.Response.Headers["Vary"] = "Origin";
            context.Response.Headers["X-Content-Type-Options"] = "nosniff";
            context.Response.Headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'self' http://127.0.0.1:* http://localhost:*";
            await next();
        });

        app.MapMethods("/{**path}", ["OPTIONS"], (HttpResponse response) =>
        {
            response.Headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS";
            response.Headers["Access-Control-Allow-Headers"] = "Content-Type";
            return Results.NoContent();
        });
        app.MapGet("/catalog.json", () => Results.Bytes(store.CatalogJson(), "application/json; charset=utf-8"));
        app.MapGet("/state.json", () => Results.Bytes(store.StateJson(), "application/json; charset=utf-8"));
        app.MapPost("/api/state", async (HttpRequest request) =>
        {
            try
            {
                using var document = await JsonDocument.ParseAsync(request.Body, cancellationToken: request.HttpContext.RequestAborted);
                var patch = ParsePatch(document.RootElement);
                var state = store.Patch(patch);
                if (patch.HasMode && patch.Mode == "rotate") state = store.Rotate(true);
                return Results.Json(state, HarnessJson.Options);
            }
            catch (JsonException) { return Results.BadRequest(); }
        });
        app.MapGet("/assets/{game}/{character}/{variant}/{side}", (HttpResponse response, string game, string character, string variant, string side) =>
        {
            if (!ValidSegment(game) || !ValidSegment(character) || !ValidSegment(variant) || (side != "light" && side != "dark"))
                return Results.NotFound();
            var key = $"/assets/{Uri.EscapeDataString(game)}/{Uri.EscapeDataString(character)}/{Uri.EscapeDataString(variant)}/{side}";
            var file = store.Asset(key);
            response.Headers["Cache-Control"] = "public, max-age=86400";
            return file is not null && File.Exists(file)
                ? Results.File(file, "image/png", enableRangeProcessing: true)
                : Results.NotFound();
        });
        app.MapGet("/", () => WebFile("index.html", "text/html; charset=utf-8"));
        app.MapGet("/app.css", () => WebFile("app.css", "text/css; charset=utf-8"));
        app.MapGet("/app.js", () => WebFile("app.js", "text/javascript; charset=utf-8"));

        application = app;
        await app.StartAsync(cancellationToken);
    }

    private IResult WebFile(string name, string contentType)
    {
        var file = Path.Combine(webRoot, name);
        return File.Exists(file) ? Results.File(file, contentType) : Results.NotFound();
    }

    private static StatePatch ParsePatch(JsonElement root)
    {
        if (root.ValueKind != JsonValueKind.Object) throw new JsonException("State patch must be an object");
        var patch = new StatePatch();
        if (root.TryGetProperty("mode", out var mode))
        {
            patch.HasMode = true;
            patch.Mode = mode.ValueKind == JsonValueKind.String ? mode.GetString() : null;
        }
        if (root.TryGetProperty("selected", out var selected))
        {
            patch.HasSelected = true;
            patch.Selected = selected.ValueKind == JsonValueKind.String ? selected.GetString() : null;
        }
        if (root.TryGetProperty("intervalMs", out var interval) && interval.TryGetInt32(out var intervalValue))
        {
            patch.HasIntervalMs = true;
            patch.IntervalMs = intervalValue;
        }
        if (root.TryGetProperty("hidden", out var hidden) && hidden.ValueKind == JsonValueKind.Array)
        {
            patch.HasHidden = true;
            patch.Hidden = hidden.EnumerateArray().Where(item => item.ValueKind == JsonValueKind.String)
                .Select(item => item.GetString()).OfType<string>().Take(10_000).ToArray();
        }
        return patch;
    }

    private static bool ValidSegment(string value) =>
        !string.IsNullOrWhiteSpace(value) && value is not "." and not ".." &&
        !value.Contains('/') && !value.Contains('\\') && !value.Contains('\0');

    private static bool IsTrustedOrigin(string origin)
    {
        if (string.IsNullOrEmpty(origin) || origin == "null") return true;
        return Uri.TryCreate(origin, UriKind.Absolute, out var uri) && uri.Scheme == "http" &&
               (uri.Host == "127.0.0.1" || uri.Host == "localhost" || uri.Host == "::1");
    }

    public async ValueTask DisposeAsync()
    {
        if (application is null) return;
        await application.StopAsync(TimeSpan.FromSeconds(3));
        await application.DisposeAsync();
        application = null;
    }
}

internal static class HarnessJson
{
    internal static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
    };
}
