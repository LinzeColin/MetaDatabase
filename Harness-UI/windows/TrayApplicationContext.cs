using System.Diagnostics;
using System.Text.Json;

namespace HarnessUI;

internal sealed class TrayApplicationContext : System.Windows.Forms.ApplicationContext
{
    private readonly string dataRoot;
    private readonly HarnessStore store;
    private readonly RuntimeServer server;
    private readonly IReadOnlyDictionary<string, Label> labels;
    private readonly NotifyIcon tray;
    private readonly Control dispatcher = new();
    private readonly System.Windows.Forms.Timer rotationTimer = new() { Interval = 60_000 };
    private readonly System.Windows.Forms.Timer catalogTimer = new() { Interval = 900_000 };
    private readonly object refreshGate = new();
    private HarnessConfiguration configuration;
    private CatalogRefreshStatus refreshStatus = new("idle", "尚未刷新", 0);
    private bool refreshRunning;
    private bool exiting;

    internal TrayApplicationContext()
    {
        dataRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Harness UI");
        Directory.CreateDirectory(dataRoot);
        store = new HarnessStore(dataRoot, HarnessJson.Options);
        configuration = ReadConfiguration() ?? new HarnessConfiguration();
        labels = ReadLabels(Path.Combine(AppContext.BaseDirectory, "config", "labels.seed.json"));
        tray = new NotifyIcon
        {
            Icon = SystemIcons.Application,
            Text = "Harness UI",
            Visible = true,
        };
        tray.DoubleClick += (_, _) => OpenGallery();
        tray.ContextMenuStrip = new ContextMenuStrip();
        dispatcher.CreateControl();
        server = new RuntimeServer(
            store,
            Path.Combine(AppContext.BaseDirectory, "web"),
            () => dispatcher.BeginInvoke(new Action(() => RefreshCatalog(false))),
            RefreshStatusSnapshot);
        BuildMenu();

        try
        {
            server.StartAsync(configuration.Port).GetAwaiter().GetResult();
        }
        catch (Exception error)
        {
            MessageBox.Show(
                $"无法在 127.0.0.1:{configuration.Port} 启动素材服务。\n\n{error.Message}",
                "Harness UI 启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
            ExitThread();
            return;
        }

        rotationTimer.Tick += (_, _) =>
        {
            var before = store.GetState().Selected;
            var after = store.Rotate(false).Selected;
            if (before != after) BuildMenu();
        };
        rotationTimer.Start();
        catalogTimer.Tick += (_, _) => RefreshCatalog(false);
        catalogTimer.Start();

        if (!string.IsNullOrWhiteSpace(configuration.SourcePath))
            RefreshCatalog(false);
    }

    private void BuildMenu()
    {
        if (tray.ContextMenuStrip is not { } menu) return;
        menu.Items.Clear();
        var state = store.GetState();
        var selected = store.GetCatalog().Entries.FirstOrDefault(entry => entry.Id == state.Selected);
        menu.Items.Add(new ToolStripMenuItem($"当前：{selected?.FullLabel ?? "未选择"}") { Enabled = false });
        menu.Items.Add(new ToolStripMenuItem($"素材库：{store.GetCatalog().Count} 个变体") { Enabled = false });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("打开角色库", null, (_, _) => OpenGallery());
        menu.Items.Add("选择 SMB 素材目录…", null, (_, _) => ChooseSource());
        menu.Items.Add("刷新素材目录", null, (_, _) => RefreshCatalog(true));
        var next = new ToolStripMenuItem("换下一张", null, (_, _) =>
        {
            store.Next();
            BuildMenu();
        });
        next.ShortcutKeys = Keys.Control | Keys.Shift | Keys.N;
        menu.Items.Add(next);
        menu.Items.Add(state.Mode == "rotate" ? "停止轮播" : "开启轮播", null, (_, _) =>
        {
            var mode = store.GetState().Mode == "rotate" ? "gallery" : "rotate";
            store.Patch(new StatePatch { HasMode = true, Mode = mode });
            if (mode == "rotate") store.Rotate(true);
            BuildMenu();
        });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("检查并下载更新…", null, (_, _) => OpenReleases());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("退出 Harness UI", null, (_, _) => ExitThread());
    }

    private void ChooseSource()
    {
        using var dialog = new FolderBrowserDialog
        {
            Description = "选择 HarnessUI 素材根目录",
            UseDescriptionForTitle = true,
            InitialDirectory = configuration.SourcePath,
            ShowNewFolderButton = false,
        };
        if (dialog.ShowDialog() != DialogResult.OK) return;
        configuration.SourcePath = dialog.SelectedPath;
        WriteConfiguration();
        RefreshCatalog(true);
    }

    private void RefreshCatalog(bool showResult)
    {
        if (refreshRunning) return;
        if (string.IsNullOrWhiteSpace(configuration.SourcePath))
        {
            SetRefreshStatus("failed", "尚未选择素材目录");
            if (showResult) MessageBox.Show(HarnessConstants.DefaultUncPath, "尚未选择素材目录", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        refreshRunning = true;
        SetRefreshStatus("running", "正在读取 SMB 素材目录");
        tray.Text = "Harness UI：正在刷新素材目录";
        Task.Run(() => CatalogBuilder.Build(configuration.SourcePath, labels, configuration.Port))
            .ContinueWith(task =>
            {
                if (task.IsCompletedSuccessfully)
                {
                    try
                    {
                        store.Install(task.Result);
                        SetRefreshStatus("ready", $"已同步 {task.Result.Catalog.Count} 个变体");
                        BuildMenu();
                        if (showResult)
                        {
                            tray.BalloonTipTitle = "Harness UI";
                            tray.BalloonTipText = $"素材目录已刷新：{task.Result.Catalog.Count} 个变体";
                            tray.ShowBalloonTip(4000);
                        }
                    }
                    catch (Exception error)
                    {
                        SetRefreshStatus("failed", error.Message);
                        if (showResult) MessageBox.Show(error.Message, "素材目录刷新失败", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    }
                }
                else
                {
                    var detail = task.Exception?.GetBaseException().Message ?? "未知错误";
                    SetRefreshStatus("failed", detail);
                    if (showResult) MessageBox.Show(detail, "素材目录刷新失败", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
                refreshRunning = false;
                tray.Text = "Harness UI";
            }, TaskScheduler.FromCurrentSynchronizationContext());
    }

    private void SetRefreshStatus(string status, string message)
    {
        lock (refreshGate)
            refreshStatus = new CatalogRefreshStatus(status, message, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
    }

    private object RefreshStatusSnapshot()
    {
        lock (refreshGate) return refreshStatus;
    }

    private void OpenGallery()
    {
        Process.Start(new ProcessStartInfo($"http://127.0.0.1:{configuration.Port}/") { UseShellExecute = true });
    }

    private static void OpenReleases()
    {
        Process.Start(new ProcessStartInfo("https://github.com/LinzeColin/MetaDatabase/releases?q=harness-ui-v") { UseShellExecute = true });
    }

    private HarnessConfiguration? ReadConfiguration()
    {
        try { return JsonSerializer.Deserialize<HarnessConfiguration>(File.ReadAllBytes(Path.Combine(dataRoot, "config.json")), HarnessJson.Options); }
        catch (IOException) { return null; }
        catch (JsonException) { return null; }
    }

    private void WriteConfiguration()
    {
        var file = Path.Combine(dataRoot, "config.json");
        var temporary = file + ".tmp";
        File.WriteAllBytes(temporary, JsonSerializer.SerializeToUtf8Bytes(configuration, HarnessJson.Options));
        File.Move(temporary, file, true);
    }

    private static IReadOnlyDictionary<string, Label> ReadLabels(string file)
    {
        try
        {
            return JsonSerializer.Deserialize<Dictionary<string, Label>>(File.ReadAllBytes(file), HarnessJson.Options)
                ?? new Dictionary<string, Label>();
        }
        catch (IOException) { return new Dictionary<string, Label>(); }
        catch (JsonException) { return new Dictionary<string, Label>(); }
    }

    protected override void ExitThreadCore()
    {
        if (exiting) return;
        exiting = true;
        rotationTimer.Stop();
        rotationTimer.Dispose();
        catalogTimer.Stop();
        catalogTimer.Dispose();
        tray.Visible = false;
        tray.Dispose();
        dispatcher.Dispose();
        try { server.DisposeAsync().AsTask().GetAwaiter().GetResult(); }
        catch { }
        base.ExitThreadCore();
    }

    private sealed record CatalogRefreshStatus(string Status, string Message, long Updated);
}
