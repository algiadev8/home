return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

if lang.lean then
  vim.lsp.config("leanls", {
    on_attach = function()
      vim.keymap.localleader = "  "
      vim.keymap.set("n", "<leader><leader>i", "<cmd>LeanInfoviewToggle<CR>", { desc = "Toggle lean infoview", noremap = true })
    end,
  })
  require("lean").setup()
  vim.diagnostic.config({
    underline = true,
    virtual_text = { spacing = 4 },
    update_in_insert = true,
  })
end

end
