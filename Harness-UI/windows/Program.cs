namespace HarnessUI;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        using var mutex = new Mutex(true, @"Local\com.linzecolin.harnessui", out var isFirstInstance);
        if (!isFirstInstance)
        {
            MessageBox.Show("Harness UI 已在运行。", "Harness UI", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        ApplicationConfiguration.Initialize();
        SynchronizationContext.SetSynchronizationContext(new WindowsFormsSynchronizationContext());
        Application.Run(new TrayApplicationContext());
    }
}
