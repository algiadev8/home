return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

local function find_copilot_disable_marker(start_path)
  local path = start_path
  if not path or path == "" then
    path = vim.fn.getcwd()
  elseif vim.fn.filereadable(path) == 1 or vim.fn.isdirectory(path) == 0 then
    path = vim.fs.dirname(path)
  end

  local markers = vim.fs.find(".nvim-disable-copilot", {
    upward = true,
    path = path,
    type = "file",
  })
  return markers[1]
end

if find_copilot_disable_marker(vim.fn.getcwd()) then
  vim.g.copilot_enabled = 0
  vim.g.copilot_filetypes = { ["*"] = false }
end

vim.api.nvim_create_autocmd({ "BufReadPre", "BufNewFile", "BufEnter" }, {
  pattern = "*",
  callback = function(args)
    local path = vim.api.nvim_buf_get_name(args.buf)
    if find_copilot_disable_marker(path) then
      vim.b[args.buf].copilot_enabled = false
    end
  end,
  desc = "Disable Copilot when .nvim-disable-copilot exists in the project",
})

vim.api.nvim_create_augroup("extra-whitespace", {})
vim.api.nvim_create_autocmd({ "VimEnter", "WinEnter" }, {
  group = "extra-whitespace",
  pattern = { "*" },
  command = [[call matchadd('ExtraWhitespace', '[\u200B\u3000]')]],
})
vim.api.nvim_create_autocmd({ "ColorScheme" }, {
  group = "extra-whitespace",
  pattern = { "*" },
  command = [[highlight default ExtraWhitespace ctermbg=202 ctermfg=202 guibg=salmon]],
})

local autosave_group = vim.api.nvim_create_augroup("AutoSaveGroup", { clear = true })
vim.api.nvim_create_autocmd({ "CursorHold", "FocusLost", "BufLeave" }, {
  group = autosave_group,
  pattern = "*",
  nested = true,
  callback = function()
    local file_exists = vim.fn.filereadable(vim.fn.expand("%")) == 1
    if vim.bo.modified and vim.bo.buftype == "" and vim.bo.modifiable and file_exists then
      vim.cmd("update")
    end
  end,
  desc = "変更があったバッファを自動的に保存する",
})

local autoread_group = vim.api.nvim_create_augroup("AutoReadGroup", { clear = true })
vim.api.nvim_create_autocmd({ "FocusGained", "BufEnter", "CursorHold", "CursorHoldI" }, {
  group = autoread_group,
  pattern = "*",
  callback = function()
    if vim.bo.buftype ~= "" then
      return
    end
    vim.cmd("checktime")
  end,
  desc = "外部で更新されたファイルを自動的に再読込する",
})


end
