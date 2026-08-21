namespace HarnessUI.Tests;

public sealed class HarnessStoreTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), $"harness-ui-store-{Guid.NewGuid():N}");

    [Fact]
    public void PatchesOnlySupportedFieldsAndKeepsSelectionInCatalog()
    {
        var store = new HarnessStore(root, HarnessJson.Options);
        var entries = new[]
        {
            new CatalogEntry("one", "genshin", "原神", "one", "default", "一", "默认", "一", "一", "light", "dark"),
            new CatalogEntry("two", "genshin", "原神", "two", "default", "二", "默认", "二", "二", "light", "dark"),
        };
        store.Install(new CatalogBuild(new Catalog(1, "smb", "now", 2, entries), new Dictionary<string, string>()));

        var state = store.Patch(new StatePatch { HasSelected = true, Selected = "two", HasIntervalMs = true, IntervalMs = 1 }, 42);

        Assert.Equal("two", state.Selected);
        Assert.Equal(14_400_000, state.IntervalMs);
        Assert.Equal(42, state.Updated);
    }

    [Fact]
    public void RotationVisitsACompleteCycleBeforeRefilling()
    {
        var store = new HarnessStore(root, HarnessJson.Options);
        var entries = Enumerable.Range(1, 3).Select(index =>
            new CatalogEntry(index.ToString(), "genshin", "原神", index.ToString(), "default", index.ToString(), "默认", index.ToString(), index.ToString(), "light", "dark")).ToArray();
        store.Install(new CatalogBuild(new Catalog(1, "smb", "now", 3, entries), new Dictionary<string, string>()));
        store.Patch(new StatePatch { HasMode = true, Mode = "rotate" }, 1);

        var seen = Enumerable.Range(1, 3).Select(index => store.Rotate(true, index + 1L).Selected).ToHashSet();

        Assert.Equal(3, seen.Count);
    }

    public void Dispose()
    {
        if (Directory.Exists(root)) Directory.Delete(root, true);
    }
}
