namespace HarnessUI.Tests;

public sealed class CatalogBuilderTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), $"harness-ui-tests-{Guid.NewGuid():N}");

    [Fact]
    public void BuildsOnlyCompleteSkinVariants()
    {
        var complete = Path.Combine(root, "原神", "aino", "skins", "default");
        var incomplete = Path.Combine(root, "原神", "aino", "skins", "missing-dark");
        Directory.CreateDirectory(complete);
        Directory.CreateDirectory(incomplete);
        File.WriteAllText(Path.Combine(complete, "light.png"), "fixture");
        File.WriteAllText(Path.Combine(complete, "dark.png"), "fixture");
        File.WriteAllText(Path.Combine(incomplete, "light.png"), "fixture");

        var labels = new Dictionary<string, Label>
        {
            ["genshin/aino/default"] = new("爱诺", "默认"),
        };
        var build = CatalogBuilder.Build(root, labels, 3099);

        Assert.Single(build.Catalog.Entries);
        Assert.Equal("genshin/aino/default", build.Catalog.Entries[0].Id);
        Assert.Equal("爱诺", build.Catalog.Entries[0].FullLabel);
        Assert.Equal(2, build.Assets.Count);
    }

    public void Dispose()
    {
        if (Directory.Exists(root)) Directory.Delete(root, true);
    }
}
