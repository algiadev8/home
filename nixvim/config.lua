local lang = {
  go = @LANG_GO_ENABLED@,
  node = @LANG_NODE_ENABLED@,
  python = @LANG_PYTHON_ENABLED@,
  rust = @LANG_RUST_ENABLED@,
  latex = @LANG_LATEX_ENABLED@,
  nix = @LANG_NIX_ENABLED@,
  ruby = @LANG_RUBY_ENABLED@,
  lean = @LANG_LEAN_ENABLED@,
  haskell = @LANG_HASKELL_ENABLED@,
}
local clipboard_provider = "@CLIPBOARD_PROVIDER@"
local python_dap_python = "@PYTHON_DAP_PYTHON@"

local config_lua_dir = "@CONFIG_LUA_DIR@"
local ctx = {
  lang = lang,
  clipboard_provider = clipboard_provider,
  python_dap_python = python_dap_python,
}

package.path = config_lua_dir .. "/?.lua;" .. config_lua_dir .. "/?/init.lua;" .. package.path

for _, name in ipairs({
  "autocmds",
  "clipboard",
  "keymaps",
  "ui",
  "completion",
  "dap",
  "plugins",
  "treesitter",
  "trouble-which-key",
  "lsp",
  "rust",
  "lean",
}) do
  require("myconfig." .. name)(ctx)
end
