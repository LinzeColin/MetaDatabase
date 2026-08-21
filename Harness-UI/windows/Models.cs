using System.Text.Json.Serialization;

namespace HarnessUI;

internal static class HarnessConstants
{
    internal const ushort DefaultPort = 3099;
    internal const string DefaultSmbUrl = "smb://192.168.0.1/share/03_资料库/MetaData/HarnessUI/";
    internal const string DefaultUncPath = @"\\192.168.0.1\share\03_资料库\MetaData\HarnessUI";

    internal static readonly KeyValuePair<string, string>[] Games =
    [
        new("原神", "genshin"),
        new("崩铁", "hsr"),
        new("绝区零", "zzz"),
        new("鸣潮", "wuwa"),
        new("异环", "nte"),
    ];
}

internal sealed record Label(string CharacterZh, string VariantZh);

internal sealed record CatalogEntry(
    string Id,
    string Game,
    string GameName,
    string Character,
    string Variant,
    string CharacterZh,
    string VariantZh,
    string Label,
    string FullLabel,
    string Light,
    string Dark);

internal sealed record Catalog(
    int Version,
    string Source,
    string Generated,
    int Count,
    CatalogEntry[] Entries)
{
    internal static readonly Catalog Empty = new(1, "smb", "", 0, []);
}

internal sealed record HarnessState
{
    public int Version { get; init; } = 1;
    public string Mode { get; set; } = "gallery";
    public string? Selected { get; set; }
    public int IntervalMs { get; set; } = 14_400_000;
    public string[] Hidden { get; set; } = [];
    public string[] Cycle { get; set; } = [];
    public int Cursor { get; set; }
    public long LastRotate { get; set; }
    public long Updated { get; set; }
    public string CatalogGenerated { get; set; } = "";
}

internal sealed record HarnessConfiguration
{
    public int Version { get; init; } = 1;
    public ushort Port { get; init; } = HarnessConstants.DefaultPort;
    public string SmbUrl { get; init; } = HarnessConstants.DefaultSmbUrl;
    public string SourcePath { get; set; } = HarnessConstants.DefaultUncPath;
}

internal sealed record CatalogBuild(Catalog Catalog, IReadOnlyDictionary<string, string> Assets);

internal sealed class StatePatch
{
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool HasMode { get; set; }
    public string? Mode { get; set; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool HasSelected { get; set; }
    public string? Selected { get; set; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool HasIntervalMs { get; set; }
    public int IntervalMs { get; set; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)] public bool HasHidden { get; set; }
    public string[] Hidden { get; set; } = [];
}
