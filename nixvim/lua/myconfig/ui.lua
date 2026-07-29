return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

require("tokyonight").setup({
  style = "night",
  on_colors = function(colors)
    colors.bg = "#011628"
    colors.bg_dark = "#011423"
  end,
  on_highlights = function(hl, colors)
    -- Python: self / cls を赤 + italic で目立たせる (tree-sitter & LSP semantic tokens)
    hl["@variable.builtin.python"] = { fg = colors.red, italic = true }
    hl["@lsp.type.selfParameter.python"] = { fg = colors.red, italic = true }
    hl["@lsp.type.clsParameter.python"] = { fg = colors.red, italic = true }
    -- Python: デコレータ
    hl["@lsp.type.decorator.python"] = { fg = colors.yellow }
    -- Python: ドキュメント文字列をコメント色 + italic に
    hl["@string.documentation.python"] = { fg = colors.comment, italic = true }
    -- Python: 組み込み関数 (print, len, range ...) を cyan に
    hl["@function.builtin.python"] = { fg = colors.cyan }
    hl["@lsp.typemod.function.defaultLibrary.python"] = { fg = colors.cyan }
    -- Python: 組み込み型 (int, str, list ...) を yellow に
    hl["@type.builtin.python"] = { fg = colors.yellow }
    hl["@lsp.typemod.class.defaultLibrary.python"] = { fg = colors.yellow, bold = true }
    -- Python: マジックメソッド (__init__ 等) を magenta に
    hl["@lsp.typemod.function.magic.python"] = { fg = colors.magenta }
    hl["@lsp.typemod.method.magic.python"] = { fg = colors.magenta }
    hl.RainbowDelimiterRed = { fg = colors.red }
    hl.RainbowDelimiterYellow = { fg = colors.yellow }
    hl.RainbowDelimiterBlue = { fg = colors.blue }
    hl.RainbowDelimiterOrange = { fg = colors.orange }
    hl.RainbowDelimiterGreen = { fg = colors.green }
    hl.RainbowDelimiterViolet = { fg = colors.purple }
    hl.RainbowDelimiterCyan = { fg = colors.cyan }
  end,
})
vim.cmd("colorscheme tokyonight")

local alpha = require("alpha")
local dashboard = require("alpha.themes.dashboard")
dashboard.section.header.val = {
  "                                                     ",
  "  ███╗   ██╗███████╗ ██████╗ ██╗   ██╗██╗███╗   ███╗ ",
  "  ████╗  ██║██╔════╝██╔═══██╗██║   ██║██║████╗ ████║ ",
  "  ██╔██╗ ██║█████╗  ██║   ██║██║   ██║██║██╔████╔██║ ",
  "  ██║╚██╗██║██╔══╝  ██║   ██║╚██╗ ██╔╝██║██║╚██╔╝██║ ",
  "  ██║ ╚████║███████╗╚██████╔╝ ╚████╔╝ ██║██║ ╚═╝ ██║ ",
  "  ╚═╝  ╚═══╝╚══════╝ ╚═════╝   ╚═══╝  ╚═╝╚═╝     ╚═╝ ",
  "                                                     ",
}
dashboard.section.buttons.val = {
  dashboard.button("e", "  > New File", "<cmd>ene<CR>"),
  dashboard.button("SPC ee", "  > Toggle file explorer", "<cmd>NvimTreeToggle<CR>"),
  dashboard.button("SPC ff", "󰱼 > Find File", "<cmd>Telescope find_files<CR>"),
  dashboard.button("SPC fs", "  > Find Word", "<cmd>Telescope live_grep<CR>"),
  dashboard.button("SPC wr", "󰁯  > Restore Session For Current Directory", "<cmd>SessionRestore<CR>"),
  dashboard.button("q", " > Quit NVIM", "<cmd>qa<CR>"),
}
alpha.setup(dashboard.opts)
vim.cmd([[autocmd FileType alpha setlocal nofoldenable]])

require("auto-session").setup({
  auto_restore_enabled = false,
  auto_session_suppress_dirs = { "~/", "~/Dev/", "~/Downloads", "~/Documents", "~/Desktop/" },
})
vim.keymap.set("n", "<leader>wr", "<cmd>SessionRestore<CR>", { desc = "Restore session for cwd" })
vim.keymap.set("n", "<leader>ws", "<cmd>SessionSave<CR>", { desc = "Save session for auto session root dir" })

end
