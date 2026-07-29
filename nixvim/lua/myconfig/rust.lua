return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

if lang.rust then
  vim.g.rustaceanvim = {
    server = {
      default_settings = {
        ["rust-analyzer"] = {
          cargo = {
            autoreload = true,
            allTargets = false,
            allFeatures = false,
            buildScripts = { enable = true },
          },
          -- procMacro = { enable = true },
          -- files = { watcher = "client" },
          -- checkOnSave = { command = "clippy", extraArgs = { "--all", "--", "-W", "clippy::all" } },
          diagnostics = { disabled = { "E0308", "E0605" } },
          inlayHints = {
            closureCaptureHints = { enable = true },
            closureReturnTypeHints = { enable = "always" },
            expressionAdjustmentHints = { enable = "always" },
            lifetimeElisionHints = { enable = "skip_trivial" },
            rangeExclusiveHints = { enable = true },
            reborrowHints = { enable = "always" },
          },
        },
      },
    },
  }
  vim.api.nvim_create_autocmd("FileType", {
    pattern = "rust",
    callback = function(args)
      local function run_rust_with_args()
        local input = vim.fn.input("cargo run args: ")
        local cmd = { "runnables" }
        for _, arg in ipairs(vim.split(input, "%s+", { trimempty = true })) do
          table.insert(cmd, arg)
        end
        vim.cmd.RustLsp(cmd)
      end
      vim.keymap.set("n", "K", function() vim.cmd.RustLsp({ "hover", "actions" }) end, { silent = true, buffer = args.buf })
      vim.keymap.set("n", "<leader>rr", run_rust_with_args, { silent = true, buffer = args.buf, desc = "Run Rust project with args" })
      vim.keymap.set("n", "<leader>rd", function() vim.cmd.RustLsp("debuggables") end, { silent = true, buffer = args.buf, desc = "Debug Rust project" })
      vim.keymap.set("n", "<leader>rt", function() vim.cmd.RustLsp("testables") end, { silent = true, buffer = args.buf, desc = "Run Rust tests" })
    end,
  })
end

end
