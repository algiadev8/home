return function(ctx)
local lang = ctx.lang
local clipboard_provider = ctx.clipboard_provider
local python_dap_python = ctx.python_dap_python

vim.api.nvim_create_autocmd("LspAttach", {
  group = vim.api.nvim_create_augroup("UserLspConfig", {}),
  callback = function(ev)
    local opts = { buffer = ev.buf, silent = true }
    opts.desc = "Show LSP references"
    vim.keymap.set("n", "gR", "<cmd>Telescope lsp_references<CR>", opts)
    opts.desc = "Go to declaration"
    vim.keymap.set("n", "gD", vim.lsp.buf.declaration, opts)
    opts.desc = "Show LSP definitions"
    vim.keymap.set("n", "gd", "<cmd>Telescope lsp_definitions<CR>", opts)
    opts.desc = "Show LSP implementations"
    vim.keymap.set("n", "gi", "<cmd>Telescope lsp_implementations<CR>", opts)
    opts.desc = "Show LSP type definitions"
    vim.keymap.set("n", "gt", "<cmd>Telescope lsp_type_definitions<CR>", opts)
    opts.desc = "See available code actions"
    vim.keymap.set({ "n", "v" }, "<leader>ca", vim.lsp.buf.code_action, opts)
    opts.desc = "Smart rename"
    vim.keymap.set("n", "<leader>rn", vim.lsp.buf.rename, opts)
    opts.desc = "Show buffer diagnostics"
    vim.keymap.set("n", "<leader>gdD", "<cmd>Telescope diagnostics bufnr=0<CR>", opts)
    opts.desc = "Show line diagnostics"
    vim.keymap.set("n", "<leader>gdd", vim.diagnostic.open_float, opts)
    opts.desc = "Go to previous diagnostic"
    vim.keymap.set("n", "[d", vim.diagnostic.goto_prev, opts)
    opts.desc = "Go to next diagnostic"
    vim.keymap.set("n", "]d", vim.diagnostic.goto_next, opts)
    opts.desc = "Show documentation for what is under cursor"
    vim.keymap.set("n", "K", vim.lsp.buf.hover, opts)
    opts.desc = "Restart LSP"
    vim.keymap.set("n", "<leader>rs", function()
      local clients = vim.lsp.get_clients({ bufnr = ev.buf })
      if #clients == 0 then
        vim.notify("No active LSP clients for this buffer", vim.log.levels.INFO)
        return
      end

      local client_names = {}
      for _, client in ipairs(clients) do
        client_names[client.name] = true
        client:stop(true)
      end

      vim.defer_fn(function()
        for name in pairs(client_names) do
          pcall(vim.lsp.enable, name, true)
        end
        vim.cmd("edit")
      end, 500)
    end, opts)
    opts.desc = "Toggle LSP inlay hints"
    vim.keymap.set("n", "<leader>li", function()
      vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled())
    end, opts)
  end,
})

require("lsp-file-operations").setup()
require("neodev").setup()
vim.lsp.config("*", {
  capabilities = vim.tbl_deep_extend(
    "force",
    require("blink.cmp").get_lsp_capabilities(),
    { general = { positionEncodings = { "utf-8" } } }
  ),
})
local signs = { Error = " ", Warn = " ", Hint = "󰠠 ", Info = " " }
for type, icon in pairs(signs) do
  local hl = "DiagnosticSign" .. type
  vim.fn.sign_define(hl, { text = icon, texthl = hl, numhl = "" })
end
vim.lsp.config("lua_ls", {
  settings = { Lua = { diagnostics = { globals = { "vim" } }, completion = { callSnippet = "Replace" } } },
})
if lang.node then
  vim.lsp.config("ts_ls", {
    init_options = {
      preferences = {
        includeInlayParameterNameHints = "all",
        includeInlayParameterNameHintsWhenArgumentMatchesName = true,
        includeInlayFunctionParameterTypeHints = true,
        includeInlayVariableTypeHints = true,
        includeInlayPropertyDeclarationTypeHints = true,
        includeInlayFunctionLikeReturnTypeHints = true,
        includeInlayEnumMemberValueHints = true,
        importModuleSpecifierPreference = "non-relative",
      },
    },
  })
end
if lang.nix then
  vim.lsp.config("nil_ls", { formatting = { command = { "nixfmt" } } })
end
if lang.latex then
  vim.lsp.config("texlab", {
    root_markers = { ".texlabroot", "texlabroot", ".latexmkrc", "latexmkrc", "Tectonic.toml", ".git" },
    settings = {
      texlab = {
        build = {
          executable = "latexmk",
          args = {
            "-pdf",
            "-interaction=nonstopmode",
            "-synctex=1",
            "%f",
          },
          onSave = false,
          useFileList = true,
        },
        chktex = {
          onOpenAndSave = false,
          onEdit = false,
        },
        diagnosticsDelay = 300,
      },
    },
  })

  vim.g.vimtex_compiler_method = "latexmk"
  vim.g.vimtex_compiler_latexmk = {
    continuous = 0,
    options = {
      "-pdf",
      "-verbose",
      "-file-line-error",
      "-synctex=1",
      "-interaction=nonstopmode",
    },
  }
  vim.g.vimtex_quickfix_mode = 2
  vim.g.vimtex_quickfix_open_on_warning = 0
  vim.g.vimtex_quickfix_autojump = 0
  vim.g.vimtex_syntax_conceal_disable = 0
  vim.opt.conceallevel = 0
  vim.opt.concealcursor = "nc"

  -- VimTeX conceal の切り替え
  vim.keymap.set("n", "<localleader>lz", function()
    vim.wo.conceallevel = vim.wo.conceallevel == 0 and 2 or 0
    vim.wo.concealcursor = "nc"
  end, { desc = "Toggle VimTeX conceal" })

  -- nabla.nvim の数式プレビュー切り替え
  vim.keymap.set("n", "<localleader>ln", function()
    require("nabla").toggle_virt({ autogen = true, silent = true })
  end, { desc = "Toggle Nabla math preview" })
end
if lang.go then
  vim.lsp.config("gopls", {
    root_markers = { "go.work", "go.mod", ".git" },
    settings = {
      gopls = {
        completeUnimported = true,
        gofumpt = true,
        staticcheck = true,
        usePlaceholders = true,
        hints = {
          assignVariableTypes = true,
          compositeLiteralFields = true,
          compositeLiteralTypes = true,
          constantValues = true,
          functionTypeParameters = true,
          parameterNames = true,
          rangeVariableTypes = true,
        },
      },
    },
  })
end
if lang.python then
  vim.lsp.config("basedpyright", {
    settings = {
      basedpyright = {
        analysis = {
          autoImportCompletions = true,
          autoSearchPaths = true,
          diagnosticMode = "workspace",
          inlayHints = {
            callArgumentNames = true,
            functionReturnTypes = true,
            genericTypes = true,
            variableTypes = true,
          },
          typeCheckingMode = "standard",
          useLibraryCodeForTypes = true,
        },
      },
      python = {
        analysis = {
          autoImportCompletions = true,
          autoSearchPaths = true,
          diagnosticMode = "workspace",
          typeCheckingMode = "standard",
          useLibraryCodeForTypes = true,
        },
      },
    },
  })
  vim.lsp.config("ruff", {
    init_options = {
      settings = {
        organizeImports = true,
      },
    },
    on_attach = function(client)
      client.server_capabilities.hoverProvider = false
    end,
  })
end
if lang.ruby then
  vim.lsp.config("ruby_lsp", {
    filetypes = { "ruby" },
    cmd = { "ruby-lsp" },
    root_markers = { "gemfile", ".git" },
    init_options = { formatter = "standard", linters = { "standard" } },
  })
  vim.lsp.config("solargraph", {
    filetypes = { "ruby" },
    cmd = { "solargraph", "stdio" },
    root_markers = { "gemfile", ".git" },
    init_options = { formatting = true },
  })
end
if lang.haskell then
  vim.g.haskell_tools = {
    hls = {
      capabilities = require("blink.cmp").get_lsp_capabilities(),
      on_attach = function(_, bufnr, ht)
        local opts = { noremap = true, silent = true, buffer = bufnr }
        vim.keymap.set("n", "<localleader>cl", vim.lsp.codelens.run, vim.tbl_extend("force", opts, { desc = "Run Haskell code lens" }))
        vim.keymap.set("n", "<localleader>ea", ht.lsp.buf_eval_all, vim.tbl_extend("force", opts, { desc = "Evaluate Haskell snippets" }))
        vim.keymap.set("n", "<localleader>hs", ht.hoogle.hoogle_signature, vim.tbl_extend("force", opts, { desc = "Hoogle signature search" }))
        vim.keymap.set("n", "<localleader>rr", ht.repl.toggle, vim.tbl_extend("force", opts, { desc = "Toggle Haskell REPL" }))
        vim.keymap.set("n", "<localleader>rf", function()
          ht.repl.toggle(vim.api.nvim_buf_get_name(0))
        end, vim.tbl_extend("force", opts, { desc = "Toggle Haskell buffer REPL" }))
        vim.keymap.set("n", "<localleader>rq", ht.repl.quit, vim.tbl_extend("force", opts, { desc = "Quit Haskell REPL" }))
      end,
    },
  }
end
vim.lsp.config("typos_lsp", {
  cmd = { "typos-lsp" },
  init_options = { config = "@TYPOS_CONFIG@" },
})
vim.lsp.config("harper_ls", {
  cmd = { "harper-ls", "--stdio" },
  filetypes = { "gitcommit", "latex", "markdown", "norg", "org", "plaintex", "rst", "tex", "text", "typst" },
  handlers = {
    ["textDocument/publishDiagnostics"] = function(err, result, ctx, config)
      if result and result.diagnostics then
        local bufnr = vim.uri_to_bufnr(result.uri)
        local ft = vim.bo[bufnr].filetype
        if ft == "latex" or ft == "tex" or ft == "plaintex" then
          result.diagnostics = vim.tbl_filter(function(diagnostic)
            if diagnostic.code ~= "CommaFixes" then
              return true
            end

            local row = diagnostic.range.start.line
            local col = diagnostic.range.start.character
            local line = vim.api.nvim_buf_get_lines(bufnr, row, row + 1, false)[1] or ""
            local char = line:sub(col + 1, col + 1)
            local next_char = line:sub(col + 2, col + 2)

            return char ~= "$" and next_char ~= "$"
          end, result.diagnostics)
        end
      end

      return vim.lsp.diagnostic.on_publish_diagnostics(err, result, ctx, config)
    end,
  },
  settings = {
    ["harper-ls"] = {
      diagnosticSeverity = "warning",
      linters = {
        SpellCheck = true,
      },
    },
  },
})
local lsp_servers = { "lua_ls", "harper_ls", "typos_lsp" }
if lang.node then
  vim.list_extend(lsp_servers, { "ts_ls", "html", "cssls", "tailwindcss", "graphql", "emmet_ls", "prismals" })
end
if lang.go then
  table.insert(lsp_servers, "gopls")
end
if lang.python then
  vim.list_extend(lsp_servers, { "basedpyright", "ruff" })
end
if lang.ruby then
  table.insert(lsp_servers, "solargraph")
end
if lang.nix then
  table.insert(lsp_servers, "nil_ls")
end
if lang.latex then
  table.insert(lsp_servers, "texlab")
end
for _, server in ipairs(lsp_servers) do
  pcall(vim.lsp.enable, server)
end

end
