return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

local dap = require("dap")
require("dapui").setup({ controls = { icons = { disconnect = "⏻" } } })
require("nvim-dap-virtual-text").setup()
vim.fn.sign_define("DapBreakpoint", { text = "", texthl = "", linehl = "", numhl = "" })
vim.fn.sign_define("DapBreakpointRejected", { text = "󰉥", texthl = "", linehl = "", numhl = "" })
vim.fn.sign_define("DapLogPoint", { text = "", texthl = "", linehl = "", numhl = "" })
vim.fn.sign_define("DapStopped", { text = "", texthl = "", linehl = "", numhl = "" })
vim.keymap.set("n", "<leader>du", function() require("dapui").toggle() end, { desc = "Toggle DAP UI" })
vim.keymap.set("n", "<leader>db", function() require("dap").toggle_breakpoint() end, { desc = "Toggle Breakpoint" })
vim.keymap.set("n", "<leader>dc", function() require("dap").continue() end, { desc = "DAP Continue" })
if lang.python then
  require("dap-python").setup(python_dap_python)
  require("dap-python").test_runner = "pytest"
  vim.keymap.set("n", "<leader>dpt", function() require("dap-python").test_method() end, { desc = "Debug Python test" })
  vim.keymap.set("n", "<leader>dpc", function() require("dap-python").test_class() end, { desc = "Debug Python test class" })
  vim.keymap.set("v", "<leader>dps", function() require("dap-python").debug_selection() end, { desc = "Debug Python selection" })
end

end
