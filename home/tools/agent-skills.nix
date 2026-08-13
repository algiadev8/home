{ config, lib, ... }:

let
  tools = config.my.tools;
  anyAgentToolEnabled =
    tools.claude.enable
    || tools.codex.enable
    || tools.gemini.enable
    || tools.opencode.enable
    || tools.copilot.enable
    || tools.antigravity.enable;
  agentInstructions = ''
    # Agent Instructions

    When storing user data that should persist across sessions, never use
    `~/.claude`, `~/.skills`, `~/.codex`, or other tool-specific directories.
    Use `~/.agent-memo` instead.

    This does not apply to project documentation or other project-owned files.

    ## 作業規範(全プロジェクト共通)

    - 事実・ライブラリのバージョン・API仕様は、断言する前にweb検索や実物(コード・公式ドキュメント)で検証する。検証していないことは「未検証」と明示する。
    - 情報が不足しているときは、推測で補完せずユーザーに質問する。
    - 安易に自力実装へ走らず、まず既存のライブラリを探す。候補の信頼性は、更新頻度、メンテナンス体制、GitHubのスター数などを確認して判断する。自力実装する場合は理由を先に説明する。
    - CLIで解決できる作業も、安易な回避策や自力での対応に走らず、まず適切なCLIツールを探す。必要なツールは `nix run` で実行してよい。
    - 破壊的な操作(リネーム、ファイル削除、大きな設計変更)は実行前に計画を提示して承認を得る。
    - 「修正した」と報告する前に、ビルド・実行・テストで実際に確認する。
    - 日本語の文章では誇張表現やAI的な埋め言葉を避け、根拠のある主張を控えめな接続で書く。
    - プログラムの仕様を決定する際は最低限の機能を作る．使用しない・冗長な引数，設定，機能を追加しない．

    ## ~/.agent-memo の書式

    - 1事実1ファイル(kebab-case.md)+ MEMORY.md がindex(1行1エントリ)。
    - 用途: プロジェクト横断で再発する環境固有の知見(ビルドエラーの回避策、ツールの癖など)。
    - 参照: 環境起因のエラーに遭遇したら、まず MEMORY.md を確認する。
    - 相対日付は絶対日付で記録する。
  '';

  agentMemoSeedDir = ../../dotfiles/.agent-memo;
  agentMemoFiles = [
    "MEMORY.md"
    "apple-clang-liconv.md"
    "pnpm-vite-build.md"
  ];
in
{
  config = lib.mkIf anyAgentToolEnabled {
    programs.agent-skills = {
      enable = true;

      sources.claude-my-skills = {
        input = "claude-my-skills";
        subdir = ".";
        filter.maxDepth = 1;
      };
      sources.ppt-master = {
        input = "ppt-master";
        subdir = "skills";
      };

      sources.local-skills = {
        path = ../../skills;
        subdir = ".";
        filter.maxDepth = 1;
      };

      skills.enableAll = [
        "claude-my-skills"
        "ppt-master"
        "local-skills"
      ];

      targets = {
        claude = {
          enable = tools.claude.enable;
          dest = ".claude/skills";
          structure = "link";
        };
        codex = {
          enable = tools.codex.enable;
          structure = "copy-tree";
        };
        gemini = {
          enable = tools.gemini.enable;
          structure = "copy-tree";
        };
        opencode = {
          enable = tools.opencode.enable;
          structure = "copy-tree";
        };
        copilot = {
          enable = tools.copilot.enable;
          structure = "copy-tree";
        };
        # agent-skills-nix ships a default "antigravity" target pointed at
        # $HOME/.gemini/antigravity/skills, but the installed antigravity-cli
        # package (overlays/antigravity) actually keeps its state under
        # $HOME/.gemini/antigravity-cli (settings.json, brain/, etc.) and has
        # no "skills" directory of its own yet. It's unconfirmed whether
        # antigravity-cli reads skills from a dedicated directory at all;
        # this distributes to the plausible ~/.gemini/antigravity-cli/skills
        # location so skills are ready if/when it does.
        antigravity = {
          enable = tools.antigravity.enable;
          dest = "$HOME/.gemini/antigravity-cli/skills";
          structure = "copy-tree";
        };
      };
    };

    home.file."AGENTS.md".text = agentInstructions;
    home.file."CLAUDE.md".text = agentInstructions;

    # ~/.agent-memo is written to at runtime by the agents themselves (per the
    # instructions above), so seed it once and never overwrite existing files.
    home.activation.agentMemoSeed = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      mkdir -p "$HOME/.agent-memo"
      ${lib.concatMapStringsSep "\n" (f: ''
        if [ ! -e "$HOME/.agent-memo/${f}" ]; then
          cp "${agentMemoSeedDir}/${f}" "$HOME/.agent-memo/${f}"
        fi
      '') agentMemoFiles}
    '';
  };
}
