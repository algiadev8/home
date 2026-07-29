return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

-- nvim-treesitter 0.10+ removed configs module; highlight/indent are native in nvim 0.12+
vim.api.nvim_create_autocmd("FileType", {
  callback = function(ev)
    local ft = vim.bo[ev.buf].filetype
    pcall(vim.treesitter.start, ev.buf)
    if ft ~= "latex" and ft ~= "tex" then
      vim.bo[ev.buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
    end
  end,
})
vim.treesitter.query.set("latex", "rainbow-delimiters", [[
(brack_group_key_value
  "[" @delimiter
  "]" @delimiter @sentinel) @container

(curly_group
  "{" @delimiter
  "}" @delimiter @sentinel) @container

(curly_group
  "(" @delimiter
  ")" @delimiter @sentinel) @container

(curly_group_text
  "{" @delimiter
  "}" @delimiter @sentinel) @container

(curly_group_text_list
  "{" @delimiter
  "}" @delimiter @sentinel) @container

(inline_formula
  "$" @delimiter
  "$" @delimiter @sentinel) @container

(curly_group_label
  "{" @delimiter
  "}" @delimiter @sentinel) @container

(curly_group_label_list
  "{" @delimiter
  "}" @delimiter) @container

(curly_group_path
  "{" @delimiter
  "}" @delimiter @sentinel) @container

(curly_group_path_list
  "{" @delimiter
  "}" @delimiter @sentinel) @container

(curly_group_author_list
  "{" @delimiter
  "}" @delimiter @sentinel) @container
]])
require("rainbow-delimiters.setup").setup({
  priority = {
    latex = 200,
  },
  highlight = {
    "RainbowDelimiterRed",
    "RainbowDelimiterYellow",
    "RainbowDelimiterBlue",
    "RainbowDelimiterOrange",
    "RainbowDelimiterGreen",
    "RainbowDelimiterViolet",
    "RainbowDelimiterCyan",
  },
})
vim.api.nvim_create_autocmd({ "FileType", "BufEnter" }, {
  pattern = { "tex", "plaintex", "latex" },
  callback = function(ev)
    vim.schedule(function()
      if not vim.api.nvim_buf_is_valid(ev.buf) or vim.bo[ev.buf].filetype == "" then
        return
      end
      pcall(require("rainbow-delimiters").enable, ev.buf)
    end)
  end,
})
require("nvim-ts-autotag").setup()

end
