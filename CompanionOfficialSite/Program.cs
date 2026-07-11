var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.UseDefaultFiles();
app.UseStaticFiles();

app.MapGet("/health", () => Results.Ok(new
{
    app = "CompanionOfficialSite",
    status = "ok"
}));

app.MapMethods("/download/windows", ["GET", "HEAD"], (IWebHostEnvironment env) =>
{
    var installerPath = Path.Combine(env.WebRootPath, "download", "CompanionAI-Setup.exe");
    if (!File.Exists(installerPath))
    {
        return Results.NotFound("Windows installer is not available yet.");
    }

    return Results.File(
        installerPath,
        "application/vnd.microsoft.portable-executable",
        "CompanionAI-Setup.exe");
});

IResult DetailPage(IWebHostEnvironment env, string page)
{
    var pagePath = Path.Combine(env.WebRootPath, page, "index.html");
    if (!File.Exists(pagePath))
    {
        return Results.NotFound();
    }

    return Results.File(pagePath, "text/html; charset=utf-8");
}

app.MapMethods("/features/", ["GET", "HEAD"], (IWebHostEnvironment env) => DetailPage(env, "features"));
app.MapMethods("/privacy/", ["GET", "HEAD"], (IWebHostEnvironment env) => DetailPage(env, "privacy"));
app.MapMethods("/access/", ["GET", "HEAD"], (IWebHostEnvironment env) => DetailPage(env, "access"));

app.MapFallbackToFile("index.html");

app.Run();
