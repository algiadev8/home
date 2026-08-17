return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

require("diffview").setup({
  enhanced_diff_hl = true,
  use_icons = true,
  view = {
    default = { layout = "diff2_horizontal" },
    merge_tool = { layout = "diff4_mixed", disable_diagnostics = true },
  },
})
vim.keymap.set("n", "<leader>gv", "<cmd>DiffviewOpen<cr>", { desc = "Open diff view" })
vim.keymap.set("n", "<leader>gh", "<cmd>DiffviewFileHistory %<cr>", { desc = "Open file history" })
vim.keymap.set("n", "<leader>gB", "<cmd>DiffviewOpen origin/HEAD...HEAD --imply-local<cr>", { desc = "Review branch changes" })

require("dressing").setup()
require("fusen").setup()
require("ibl").setup({ indent = { char = "┊" } })
require("markview").setup()
require("yanky").setup({
  ring = {
    history_length = 100,
    storage = "shada",
  },
})
require("nvim-surround").setup()

local formatters = {}
local formatters_by_ft = { lua = { "stylua" } }

if lang.go then
  formatters.golines = {
    command = "golines",
    args = { "--base-formatter=gofumpt" },
    stdin = true,
  }
  formatters_by_ft.go = { "goimports", "golines" }
end
if lang.node then
  vim.tbl_deep_extend("force", formatters_by_ft, {
    javascript = { "prettier" },
    typescript = { "prettier" },
    javascriptreact = { "prettier" },
    typescriptreact = { "prettier" },
    svelte = { "prettier" },
    css = { "prettier" },
    html = { "prettier" },
    json = { "prettier" },
    yaml = { "prettier" },
    markdown = { "prettier" },
    graphql = { "prettier" },
    liquid = { "prettier" },
  })
end
if lang.python then
  formatters_by_ft.python = { "ruff_organize_imports", "ruff_fix", "ruff_format" }
end
if lang.ruby then
  formatters_by_ft.eruby = { "htmlbeautifier" }
end
if lang.latex then
  formatters.latexindent = { command = "latexindent", args = { "-m" }, stdin = true }
  formatters_by_ft.tex = { "latexindent" }
end
if lang.terraform then
  formatters_by_ft.terraform = { "terraform_fmt" }
  formatters_by_ft["terraform-vars"] = { "terraform_fmt" }
end
if lang.nix then
  formatters_by_ft.nix = { "nixfmt" }
end
if lang.rust then
  formatters_by_ft.rust = { "rustfmt" }
end
if lang.haskell then
  formatters_by_ft.haskell = { "fourmolu" }
  formatters_by_ft.lhaskell = { "fourmolu" }
end

require("conform").setup({
  formatters = formatters,
  formatters_by_ft = formatters_by_ft,
  format_on_save = { lsp_format = "fallback", timeout_ms = 10000 },
  default_format_opts = { lsp_format = "fallback" },
})
vim.keymap.set({ "n", "v" }, "<leader>mp", function()
  require("conform").format({ lsp_format = "fallback", timeout_ms = 10000 })
end, { desc = "Format file or range (in visual mode)" })

require("gitsigns").setup({
  on_attach = function(bufnr)
    local gs = package.loaded.gitsigns
    local function map(mode, lhs, rhs, desc)
      vim.keymap.set(mode, lhs, rhs, { buffer = bufnr, desc = desc })
    end
    map("n", "]h", gs.next_hunk, "Next Hunk")
    map("n", "[h", gs.prev_hunk, "Prev Hunk")
    map("n", "<leader>hs", gs.stage_hunk, "Stage hunk")
    map("n", "<leader>hr", gs.reset_hunk, "Reset hunk")
    map("v", "<leader>hs", function() gs.stage_hunk({ vim.fn.line("."), vim.fn.line("v") }) end, "Stage hunk")
    map("v", "<leader>hr", function() gs.reset_hunk({ vim.fn.line("."), vim.fn.line("v") }) end, "Reset hunk")
    map("n", "<leader>hS", gs.stage_buffer, "Stage buffer")
    map("n", "<leader>hR", gs.reset_buffer, "Reset buffer")
    map("n", "<leader>hu", gs.undo_stage_hunk, "Undo stage hunk")
    map("n", "<leader>hp", gs.preview_hunk, "Preview hunk")
    map("n", "<leader>hb", function() gs.blame_line({ full = true }) end, "Blame line")
    map("n", "<leader>hB", gs.toggle_current_line_blame, "Toggle line blame")
    map("n", "<leader>hd", gs.diffthis, "Diff this")
    map("n", "<leader>hD", function() gs.diffthis("~") end, "Diff this ~")
    map({ "o", "x" }, "ih", ":<C-U>Gitsigns select_hunk<CR>", "Gitsigns select hunk")
  end,
})

local lint = require("lint")
lint.linters_by_ft = {}
if lang.node then
  lint.linters_by_ft.javascript = { "eslint_d" }
  lint.linters_by_ft.typescript = { "eslint_d" }
  lint.linters_by_ft.javascriptreact = { "eslint_d" }
  lint.linters_by_ft.typescriptreact = { "eslint_d" }
  lint.linters_by_ft.svelte = { "eslint_d" }
end
local lint_augroup = vim.api.nvim_create_augroup("lint", { clear = true })
vim.api.nvim_create_autocmd({ "BufEnter", "BufWritePost", "InsertLeave" }, {
  group = lint_augroup,
  callback = function()
    lint.try_lint()
  end,
})
vim.keymap.set("n", "<leader>l", function() lint.try_lint() end, { desc = "Trigger linting for current file" })

require("lualine").setup({
  sections = {
    lualine_c = { { "filename", path = 1 } },
    lualine_x = {
      {
        function() return require("dap").status() end,
        icon = { "", color = { fg = "#afdf00" } },
        cond = function()
          if not package.loaded.dap then return false end
          return require("dap").session() ~= nil
        end,
      },
    },
  },
  options = { disable_filetype = { winbar = { "dap-repl" } } },
})

require("nvim-tree").setup({
  view = { width = 35, relativenumber = true },
  renderer = {
    indent_markers = { enable = true },
    icons = { glyphs = { folder = { arrow_closed = "", arrow_open = "" } } },
  },
  actions = { open_file = { window_picker = { enable = false } } },
  git = { ignore = false },
  filters = { custom = { "^\\.git$", "node_modules", "^\\.cache$" } },
})
vim.keymap.set("n", "<leader>ee", "<cmd>NvimTreeToggle<CR>", { desc = "Toggle file explore" })
vim.keymap.set("n", "<leader>ef", "<cmd>NvimTreeFindFileToggle<CR>", { desc = "Toggle file explore on current file" })
vim.keymap.set("n", "<leader>ec", "<cmd>NvimTreeCollapse<CR>", { desc = "Collapse file explore" })
vim.keymap.set("n", "<leader>er", "<cmd>NvimTreeRefresh<CR>", { desc = "Refresh file explore" })

local substitute = require("substitute")
substitute.setup()
vim.keymap.set("n", "s", substitute.operator, { desc = "Substitute with motion" })
vim.keymap.set("n", "ss", substitute.line, { desc = "Substitute line" })
vim.keymap.set("n", "S", substitute.eol, { desc = "Substitute to end of line" })
vim.keymap.set("x", "s", substitute.visual, { desc = "Substitute in visual mode" })

local telescope = require("telescope")
local actions = require("telescope.actions")
telescope.setup({
  defaults = {
    path_display = { "smart" },
    mappings = { i = {
      ["<C-k>"] = actions.move_selection_previous,
      ["<C-j>"] = actions.move_selection_next,
      ["<C-q>"] = actions.send_selected_to_qflist + actions.open_qflist,
    } },
  },
  extensions = {
    fzf = {
      fuzzy = true,
      override_generic_sorter = true,
      override_file_sorter = true,
      case_mode = "smart_case",
    },
  },
})
telescope.load_extension("fzf")
telescope.load_extension("yank_history")
vim.keymap.set("n", "<leader>ff", "<cmd>Telescope find_files<cr>", { desc = "Fuzzy find files in cwd" })
vim.keymap.set("n", "<leader>fr", "<cmd>Telescope oldfiles<cr>", { desc = "Fuzzy find recent files" })
vim.keymap.set("n", "<leader>fs", "<cmd>Telescope live_grep<cr>", { desc = "Find string in cwd" })
vim.keymap.set("n", "<leader>fc", "<cmd>Telescope grep_string<cr>", { desc = "Find string under cursor in cwd" })
vim.keymap.set("n", "<leader>ft", "<cmd>TodoTelescope<cr>", { desc = "Find todos" })
vim.keymap.set("n", "<leader>fy", "<cmd>Telescope yank_history<cr>", { desc = "Fuzzy find yank history" })
vim.keymap.set("n", "<leader>fm", ":Telescope fusen marks<CR>", { desc = "Find fusen marks" })

local todo_comments = require("todo-comments")
vim.keymap.set("n", "]t", function() todo_comments.jump_next() end, { desc = "Next todo comment" })
vim.keymap.set("n", "[t", function() todo_comments.jump_prev() end, { desc = "Previous todo comment" })
todo_comments.setup()

require("toggleterm").setup({
  size = 20,
  open_mapping = [[<c-t>]],
  shade_filetypes = {},
  shade_terminals = true,
  shading_factor = 2,
  start_in_insert = true,
  insert_mappings = true,
  persist_size = true,
  direction = "horizontal",
  close_on_exit = true,
  shell = vim.o.shell,
  float_opts = { border = "curved", winblend = 0, highlights = { border = "Normal", background = "Normal" } },
  on_open = function(term)
    vim.api.nvim_buf_set_keymap(term.bufnr, "t", "<ESC>", "<C-\\><C-n>", { desc = "Exit Terminal mode", noremap = true, silent = true })
    pcall(vim.keymap.del, "t", "jk", { buffer = term.bufnr })
  end,
})
local Terminal = require("toggleterm.terminal").Terminal
local lazygit = Terminal:new({
  cmd = "lazygit",
  direction = "float",
  hidden = true,
  on_open = function(term)
    vim.cmd("startinsert!")
    vim.api.nvim_buf_set_keymap(term.bufnr, "n", "q", "<cmd>close<CR>", { noremap = true, silent = true })
    pcall(vim.keymap.del, "t", "jk", { buffer = term.bufnr })
    pcall(vim.keymap.del, "t", "<Esc>", { buffer = term.bufnr })
  end,
  on_close = function() vim.cmd("startinsert!") end,
})
function _lazygit_toggle()
  lazygit:toggle()
end
vim.api.nvim_set_keymap("n", "<leader>gg", "<cmd>lua _lazygit_toggle()<CR>", { noremap = true, silent = true })
local gh_dash = Terminal:new({
  cmd = "gh dash",
  direction = "float",
  hidden = true,
  on_open = function(term)
    vim.cmd("startinsert!")
    vim.api.nvim_buf_set_keymap(term.bufnr, "n", "q", "<cmd>close<CR>", { noremap = true, silent = true })
    pcall(vim.keymap.del, "t", "jk", { buffer = term.bufnr })
    pcall(vim.keymap.del, "t", "<Esc>", { buffer = term.bufnr })
  end,
  on_close = function() vim.cmd("startinsert!") end,
})
function _gh_dash_toggle()
  gh_dash:toggle()
end
vim.api.nvim_set_keymap("n", "<leader>gd", "<cmd>lua _gh_dash_toggle()<CR>", { noremap = true, silent = true })

end
