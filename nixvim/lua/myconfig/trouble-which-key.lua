return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

require("trouble").setup({ focus = true })
vim.keymap.set("n", "<leader>xw", "<cmd>Trouble diagnostics toggle<CR>", { desc = "Open trouble workspace diagnostics" })
vim.keymap.set("n", "<leader>xd", "<cmd>Trouble diagnostics toggle filter.buf=0<CR>", { desc = "Open trouble document diagnostics" })
vim.keymap.set("n", "<leader>xq", "<cmd>Trouble quickfix toggle<CR>", { desc = "Open trouble quickfix list" })
vim.keymap.set("n", "<leader>xl", "<cmd>Trouble loclist toggle<CR>", { desc = "Open trouble location list" })
vim.keymap.set("n", "<leader>xt", "<cmd>Trouble todo toggle<CR>", { desc = "Open todos in trouble" })

vim.keymap.set("n", "<leader>sm", "<cmd>MaximizerToggle<CR>", { desc = "Maximize/minimize a split" })
vim.keymap.set("n", "<leader>trw", "<Plug>TranslateW", { noremap = false, silent = true })
vim.keymap.set("v", "<leader>trw", "<Plug>TranslateWV", { noremap = false, silent = true })

local wk = require("which-key")
wk.add({
  { "<leader>e", group = "Explolar" },
  { "<leader>s", group = "Split window" },
  { "<leader>f", group = "Finder" },
  { "<leader>t", group = "Tabs" },
  { "<leader>x", group = "Trouble" },
  { "<leader>w", group = "Session" },
  { "<leader>h", group = "Git" },
})
vim.keymap.set("n", "<leader>?", function() require("which-key").show({ global = true }) end, { desc = "Buffer Local Keymaps (which-key)" })

end
