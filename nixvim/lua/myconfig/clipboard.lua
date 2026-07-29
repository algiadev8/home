return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

local function setup_wl_clipboard()
  if vim.fn.executable("wl-copy") == 1 and vim.fn.executable("wl-paste") == 1 then
    vim.g.clipboard = {
      name = "wl-clipboard",
      cache_enabled = 0,
      copy = { ["+"] = "wl-copy --type text/plain", ["*"] = "wl-copy --type text/plain" },
      paste = { ["+"] = "wl-paste --no-newline", ["*"] = "wl-paste --no-newline" },
    }
    return true
  end
  return false
end

local function setup_xclip_clipboard()
  if vim.fn.executable("xclip") == 1 then
    vim.g.clipboard = {
      name = "xclip",
      copy = { ["+"] = "xclip -selection clipboard", ["*"] = "xclip -selection primary" },
      paste = { ["+"] = "xclip -selection clipboard -o", ["*"] = "xclip -selection primary -o" },
    }
    return true
  end
  return false
end

if clipboard_provider == "wayland" then
  setup_wl_clipboard()
elseif clipboard_provider == "xclip" then
  setup_xclip_clipboard()
elseif clipboard_provider == "auto" then
  if vim.env.XDG_SESSION_TYPE == "wayland" or (not vim.env.XDG_SESSION_TYPE and vim.env.WAYLAND_DISPLAY) then
    setup_wl_clipboard()
  else
    setup_xclip_clipboard()
  end
end

end
