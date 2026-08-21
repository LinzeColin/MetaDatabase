using System.Globalization;
using System.Text.Json;

namespace HarnessUI;

internal static class CatalogBuilder
{
    internal static CatalogBuild Build(string sourceRoot, IReadOnlyDictionary<string, Label> labels, ushort port)
    {
        var generated = DateTimeOffset.UtcNow.ToString("O");
        var revision = Uri.EscapeDataString(generated);
        var entries = new List<CatalogEntry>();
        var assets = new Dictionary<string, string>(StringComparer.Ordinal);

        foreach (var (gameName, game) in HarnessConstants.Games)
        {
            var gameRoot = Path.Combine(sourceRoot, gameName);
            foreach (var characterRoot in ChildDirectories(gameRoot))
            {
                var character = Path.GetFileName(characterRoot);
                foreach (var variantRoot in ChildDirectories(Path.Combine(characterRoot, "skins")))
                {
                    var variant = Path.GetFileName(variantRoot);
                    var lightFile = Path.Combine(variantRoot, "light.png");
                    var darkFile = Path.Combine(variantRoot, "dark.png");
                    if (!File.Exists(lightFile) || !File.Exists(darkFile)) continue;

                    var id = $"{game}/{character}/{variant}";
                    labels.TryGetValue(id, out var label);
                    label ??= ReadLabel(Path.Combine(variantRoot, "meta.json"));
                    var characterZh = label?.CharacterZh ?? character;
                    var variantZh = label?.VariantZh ?? (variant == "default" ? "默认" : variant);
                    var prefix = $"/assets/{Uri.EscapeDataString(gameName)}/{Uri.EscapeDataString(character)}/{Uri.EscapeDataString(variant)}";
                    var light = $"{prefix}/light";
                    var dark = $"{prefix}/dark";
                    assets[light] = lightFile;
                    assets[dark] = darkFile;
                    entries.Add(new CatalogEntry(
                        id, game, gameName, character, variant, characterZh, variantZh,
                        characterZh,
                        variant == "default" ? characterZh : $"{characterZh} · {variantZh}",
                        $"http://127.0.0.1:{port}{light}?v={revision}",
                        $"http://127.0.0.1:{port}{dark}?v={revision}"));
                }
            }
        }

        entries.Sort((left, right) => CultureInfo.GetCultureInfo("zh-CN").CompareInfo.Compare(
            left.FullLabel, right.FullLabel, CompareOptions.StringSort));
        var catalog = new Catalog(1, "smb", generated, entries.Count, [.. entries]);
        return new CatalogBuild(catalog, assets);
    }

    private static string[] ChildDirectories(string root)
    {
        try
        {
            return Directory.EnumerateDirectories(root)
                .Where(path => !Path.GetFileName(path).StartsWith('.'))
                .OrderBy(Path.GetFileName, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
        catch (IOException) { return []; }
        catch (UnauthorizedAccessException) { return []; }
    }

    private static Label? ReadLabel(string file)
    {
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(file));
            var root = document.RootElement;
            if (!root.TryGetProperty("characterZh", out var character) ||
                !root.TryGetProperty("variantZh", out var variant)) return null;
            return new Label(character.GetString() ?? "", variant.GetString() ?? "");
        }
        catch (IOException) { return null; }
        catch (JsonException) { return null; }
    }
}
