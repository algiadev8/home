return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

local luasnip = require("luasnip")
local vscode_snippet_loader = require("luasnip.loaders.from_vscode")
vscode_snippet_loader.lazy_load()
local loaded_project_snippet_roots = {}

local function load_project_snippets(bufnr)
  bufnr = bufnr or 0
  local filename = vim.api.nvim_buf_get_name(bufnr)
  if filename == "" then
    return
  end

  local root = vim.fs.root(filename, { ".git", "flake.nix", "package.json" }) or vim.fs.root(filename, { ".vscode" })
  if not root or loaded_project_snippet_roots[root] then
    return
  end

  local vscode_dir = root .. "/.vscode"
  if vim.fn.isdirectory(vscode_dir) == 0 then
    loaded_project_snippet_roots[root] = true
    return
  end

  local snippet_files = vim.fs.find(function(name)
    return name:match("%.code%-snippets$")
  end, {
    path = vscode_dir,
    type = "file",
    limit = math.huge,
  })

  for _, path in ipairs(snippet_files) do
    vscode_snippet_loader.load_standalone({
      path = path,
      lazy = true,
      override_priority = 2000,
    })
  end

  loaded_project_snippet_roots[root] = true
end

vim.api.nvim_create_autocmd({ "BufReadPost", "BufNewFile" }, {
  callback = function(args)
    load_project_snippets(args.buf)
  end,
})

local default_sources = { "lsp", "path", "snippets", "buffer" }
local providers = {}

if lang.latex then
  table.insert(default_sources, "vimtex")
  providers.vimtex = {
    name = "vimtex",
    module = "blink.compat.source",
    score_offset = 100,
  }
end

require("blink.cmp").setup({
  keymap = {
    preset="enter",
    ["<Tab>"]={
      "select_next",
      "snippet_forward",
      "fallback",
    },
    ["<S-Tab>"]={
      "select_prev",
      "snippet_backward",
      "fallback"
    },
    ["<CR>"]={
      "accept",
      "fallback",
    },
  },
  snippets = {
    preset = "luasnip",
  },
  sources = {
    default = default_sources,
    providers = providers,
  },
  completion = {
    documentation = {
      auto_show = true,
      auto_show_delay_ms = 200,
    },
  },
  signature = {
    enabled = true,
  },
})

require("nvim-autopairs").setup({
  check_ts = true,
  ts_config = {
    lua = { "string" },
    javascript = { "template_string" },
    java = false,
  },
})

require("bufferline").setup({ options = { mode = "tabs", separator_style = "slant" } })
vim.keymap.set("i", "<C-L>", "<Plug>(copilot-accept-word)", { desc = "Copilot Accept Word" })
vim.keymap.set("i", "<C-J>", "<Plug>(copilot-next)", { desc = "Copilot Next Suggestion" })
vim.keymap.set("i", "<C-K>", "<Plug>(copilot-previous)", { desc = "Copilot Previous Suggestion" })

end
