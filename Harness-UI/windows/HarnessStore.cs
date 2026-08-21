using System.Text.Json;

namespace HarnessUI;

internal sealed class HarnessStore
{
    private readonly object gate = new();
    private readonly string dataRoot;
    private readonly JsonSerializerOptions json;
    private Catalog catalog = Catalog.Empty;
    private HarnessState state = new();
    private IReadOnlyDictionary<string, string> assets = new Dictionary<string, string>();

    internal HarnessStore(string dataRoot, JsonSerializerOptions json)
    {
        this.dataRoot = dataRoot;
        this.json = json;
        Directory.CreateDirectory(dataRoot);
        state = Read<HarnessState>(StateFile) ?? new HarnessState();
        catalog = Read<Catalog>(CatalogFile) ?? Catalog.Empty;
    }

    internal string CatalogFile => Path.Combine(dataRoot, "catalog.json");
    internal string StateFile => Path.Combine(dataRoot, "state.json");
    internal string ConfigFile => Path.Combine(dataRoot, "config.json");

    internal Catalog Catalog()
    {
        lock (gate) return catalog;
    }

    internal HarnessState State()
    {
        lock (gate) return Copy(state);
    }

    internal string? Asset(string requestPath)
    {
        lock (gate) return assets.TryGetValue(requestPath, out var file) ? file : null;
    }

    internal void Install(CatalogBuild build)
    {
        lock (gate)
        {
            catalog = build.Catalog;
            assets = build.Assets;
            state = Normalize(state, catalog);
            Write(CatalogFile, catalog);
            Write(StateFile, state);
        }
    }

    internal HarnessState Patch(StatePatch patch, long? now = null)
    {
        lock (gate)
        {
            if (patch.HasMode) state.Mode = patch.Mode ?? "gallery";
            if (patch.HasSelected) state.Selected = patch.Selected;
            if (patch.HasIntervalMs) state.IntervalMs = patch.IntervalMs;
            if (patch.HasHidden) state.Hidden = patch.Hidden;
            state.Updated = now ?? DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            state = Normalize(state, catalog);
            Write(StateFile, state);
            return Copy(state);
        }
    }

    internal HarnessState Rotate(bool force, long? now = null)
    {
        lock (gate)
        {
            var timestamp = now ?? DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            state = Normalize(state, catalog);
            if (state.Mode != "rotate") return Copy(state);
            if (!force && timestamp - state.LastRotate < state.IntervalMs) return Copy(state);

            if (state.Cycle.Length == 0 || state.Cursor >= state.Cycle.Length)
            {
                var hidden = state.Hidden.ToHashSet(StringComparer.Ordinal);
                state.Cycle = catalog.Entries.Select(entry => entry.Id).Where(id => !hidden.Contains(id)).ToArray();
                Random.Shared.Shuffle(state.Cycle);
                state.Cursor = 0;
            }
            if (state.Cursor >= state.Cycle.Length) return Copy(state);
            state.Selected = state.Cycle[state.Cursor++];
            state.LastRotate = timestamp;
            state.Updated = timestamp;
            Write(StateFile, state);
            return Copy(state);
        }
    }

    internal byte[] CatalogJson()
    {
        lock (gate) return JsonSerializer.SerializeToUtf8Bytes(catalog, json);
    }

    internal byte[] StateJson()
    {
        lock (gate) return JsonSerializer.SerializeToUtf8Bytes(state, json);
    }

    private HarnessState Normalize(HarnessState input, Catalog currentCatalog)
    {
        var ids = currentCatalog.Entries.Select(entry => entry.Id).ToHashSet(StringComparer.Ordinal);
        var hidden = input.Hidden.Where(ids.Contains).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray();
        var hiddenSet = hidden.ToHashSet(StringComparer.Ordinal);
        var cycle = input.Cycle.Where(id => ids.Contains(id) && !hiddenSet.Contains(id)).Distinct(StringComparer.Ordinal).ToArray();
        var selected = input.Selected;
        if (selected is null || !ids.Contains(selected) || hiddenSet.Contains(selected))
            selected = currentCatalog.Entries.FirstOrDefault(entry => !hiddenSet.Contains(entry.Id))?.Id;
        return input with
        {
            Mode = input.Mode == "rotate" ? "rotate" : "gallery",
            Selected = selected,
            IntervalMs = input.IntervalMs >= 60_000 ? input.IntervalMs : 14_400_000,
            Hidden = hidden,
            Cycle = cycle,
            Cursor = Math.Clamp(input.Cursor, 0, cycle.Length),
        };
    }

    private T? Read<T>(string file)
    {
        try { return JsonSerializer.Deserialize<T>(File.ReadAllBytes(file), json); }
        catch (IOException) { return default; }
        catch (JsonException) { return default; }
    }

    private void Write<T>(string file, T value)
    {
        var temporary = file + ".tmp";
        File.WriteAllBytes(temporary, JsonSerializer.SerializeToUtf8Bytes(value, json));
        File.Move(temporary, file, true);
    }

    private static HarnessState Copy(HarnessState value) => value with
    {
        Hidden = [.. value.Hidden],
        Cycle = [.. value.Cycle],
    };
}
