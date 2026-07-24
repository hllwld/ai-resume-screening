<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  NAlert,
  NButton,
  NCheckbox,
  NConfigProvider,
  NIcon,
  NInput,
  NMessageProvider,
  NProgress,
  NSpin,
  NTag,
  zhCN,
  dateZhCN,
} from "naive-ui";
import { PlayerPlay, PlayerStop, ShieldCheck, Stars } from "@vicons/tabler";
import FilePanel from "./components/FilePanel.vue";
import ResultTable from "./components/ResultTable.vue";
import {
  cancelBatch,
  createBatch,
  deleteBatch,
  getBatch,
  getSession,
  login,
  logout,
} from "./api";
import type { BatchTask, ParsedResume, SessionStatus } from "./types";

const resumes = ref<ParsedResume[]>([]);
const jobDescription = ref("");
const customInstructions = ref("");
const task = ref<BatchTask | null>(null);
const submitting = ref(false);
const session = ref<SessionStatus | null>(null);
const sessionLoading = ref(true);
const accessCode = ref("");
const authError = ref("");
const actionError = ref("");
const privacyAccepted = ref(false);
let poller: number | null = null;

const authProviderLabel = computed(() =>
  session.value?.auth_provider === "feishu" ? "飞书登录" : "口令登录",
);
const readyResumes = computed(() => resumes.value.filter((file) => file.state === "ready"));
const isRunning = computed(() => task.value?.status === "running" || task.value?.status === "pending");
const quota = computed(() => task.value?.quota || session.value?.quota);
const quotaAllowsBatch = computed(
  () =>
    Boolean(quota.value) &&
    readyResumes.value.length <= quota.value!.per_ip_remaining &&
    readyResumes.value.length <= quota.value!.global_remaining,
);
const progress = computed(() => {
  if (!task.value?.items.length) return 0;
  const finished = task.value.items.filter((item) =>
    ["success", "failed", "cancelled"].includes(item.status),
  ).length;
  return Math.round((finished / task.value.items.length) * 100);
});

function stopPolling() {
  if (poller !== null) {
    window.clearInterval(poller);
    poller = null;
  }
}

async function pollTask() {
  if (!task.value) return;
  try {
    task.value = await getBatch(task.value.task_id);
    if (["completed", "cancelled"].includes(task.value.status)) stopPolling();
  } catch {
    stopPolling();
  }
}

function startPolling() {
  stopPolling();
  poller = window.setInterval(pollTask, 1000);
}

async function startEvaluation() {
  if (!readyResumes.value.length || jobDescription.value.trim().length < 20) return;
  submitting.value = true;
  actionError.value = "";
  try {
    task.value = await createBatch(
      jobDescription.value.trim(),
      customInstructions.value.trim(),
      readyResumes.value,
    );
    if (task.value.quota && session.value) session.value.quota = task.value.quota;
    startPolling();
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : "创建任务失败";
  } finally {
    submitting.value = false;
  }
}

async function stopEvaluation() {
  if (!task.value) return;
  task.value = await cancelBatch(task.value.task_id);
}

async function loadSession() {
  sessionLoading.value = true;
  try {
    session.value = await getSession();
  } catch (error) {
    authError.value = error instanceof Error ? error.message : "无法连接服务器";
  } finally {
    sessionLoading.value = false;
  }
}

async function submitLogin() {
  authError.value = "";
  try {
    session.value = await login(accessCode.value);
    accessCode.value = "";
  } catch (error) {
    authError.value = error instanceof Error ? error.message : "登录失败";
  }
}

function startFeishuLogin() {
  window.location.assign("/api/auth/feishu/start");
}

function readAuthCallbackError() {
  const url = new URL(window.location.href);
  const errorCode = url.searchParams.get("auth_error");
  if (!errorCode) return;
  const messages: Record<string, string> = {
    cancelled: "飞书授权已取消，请重试或使用访问口令。",
    invalid_state: "飞书登录请求已失效，请重新发起登录。",
    token_failed: "飞书授权凭证获取失败，请稍后重试。",
    user_unavailable: "无法获取飞书用户身份，请确认应用权限和可用范围。",
    provider_unavailable: "飞书登录服务暂时不可用，请稍后重试。",
    disabled: "飞书登录当前未启用，请使用访问口令。",
  };
  authError.value = messages[errorCode] || "飞书登录失败，请稍后重试。";
  url.searchParams.delete("auth_error");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

async function signOut() {
  stopPolling();
  if (task.value) {
    try {
      await deleteBatch(task.value.task_id);
    } catch {
      // 任务可能已经过期；退出仍应继续。
    }
  }
  await logout();
  task.value = null;
  session.value = await getSession();
}

async function removeTask() {
  if (!task.value) return;
  actionError.value = "";
  try {
    await deleteBatch(task.value.task_id);
    task.value = null;
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : "删除任务失败";
  }
}

onMounted(() => {
  readAuthCallbackError();
  void loadSession();
});
onBeforeUnmount(stopPolling);
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider>
      <div v-if="sessionLoading" class="auth-screen">
        <NSpin size="large" />
        <span>正在连接评估服务…</span>
      </div>

      <div v-else-if="!session?.authenticated" class="auth-screen">
        <section class="auth-card">
          <span class="brand-mark"><NIcon :component="Stars" /></span>
          <span class="hero-kicker">Private demo</span>
          <h1>简历评估工作台</h1>
          <p>企业测试成员可使用飞书登录，其他访客可使用访问口令。</p>
          <NAlert v-if="authError" type="error" :show-icon="false">{{ authError }}</NAlert>
          <NButton
            v-if="session?.auth_methods.feishu"
            type="primary"
            size="large"
            @click="startFeishuLogin"
          >
            使用飞书登录
          </NButton>
          <div
            v-if="session?.auth_methods.feishu && session?.auth_methods.access_code"
            class="auth-divider"
          >
            <span>或</span>
          </div>
          <template v-if="session?.auth_methods.access_code">
            <NInput
              v-model:value="accessCode"
              type="password"
              show-password-on="click"
              placeholder="访问口令"
              size="large"
              @keyup.enter="submitLogin"
            />
            <NButton size="large" :disabled="!accessCode" @click="submitLogin">
              使用访问口令
            </NButton>
          </template>
          <small v-if="session?.auth_methods.feishu" class="auth-hint">
            飞书登录仅支持已加入企业应用可用范围的成员
          </small>
        </section>
      </div>

      <div v-else class="app-shell">
        <header class="topbar">
          <a class="brand" href="/">
            <span class="brand-mark"><NIcon :component="Stars" /></span>
            <span>
              <strong>简历评估工作台</strong>
              <small>AI-assisted candidate review</small>
            </span>
          </a>
          <div class="topbar-actions">
            <div v-if="session.display_name" class="session-identity">
              <strong>{{ session.display_name }}</strong>
              <span>{{ authProviderLabel }}</span>
            </div>
            <NTag round :bordered="false" class="safety-tag">
              <template #icon><NIcon :component="ShieldCheck" /></template>
              今日剩余 {{ quota?.per_ip_remaining ?? 0 }} 份 / 全站
              {{ quota?.global_remaining ?? 0 }} 份
            </NTag>
            <NButton v-if="session.auth_required" text @click="signOut">退出</NButton>
          </div>
        </header>

        <main>
          <section class="hero">
            <div>
              <span class="hero-kicker">Dify Workflow · Batch Review</span>
              <h1>把简历初筛，变成一张<br /><em>清晰可复核</em>的工作表</h1>
              <p>
                批量读取本地 PDF，按岗位要求生成带证据的匹配分析。原始文件不上传，
                只发送浏览器提取的文本。
              </p>
            </div>
            <div class="hero-metrics">
              <div><strong>40%</strong><span>技能匹配</span></div>
              <div><strong>25%</strong><span>相关经验</span></div>
              <div><strong>20%</strong><span>项目相关</span></div>
              <div><strong>15%</strong><span>综合质量</span></div>
            </div>
          </section>

          <div class="workspace-grid">
            <FilePanel v-model:files="resumes" :disabled="isRunning" />

            <section class="panel brief-panel">
              <div class="panel-heading">
                <div>
                  <span class="eyebrow">02 / 评价标准</span>
                  <h2>填写岗位要求</h2>
                  <p>岗位 JD 决定匹配标准，补充要求不会覆盖固定安全规则。</p>
                </div>
              </div>
              <label class="field-label" for="jd">
                岗位 JD <b>必填</b>
              </label>
              <NInput
                id="jd"
                v-model:value="jobDescription"
                type="textarea"
                :autosize="{ minRows: 8, maxRows: 13 }"
                maxlength="20000"
                show-count
                :disabled="isRunning"
                placeholder="粘贴岗位职责、必备技能、经验要求和不可妥协条件…"
              />
              <label class="field-label optional" for="prompt">
                补充评价要求 <span>选填</span>
              </label>
              <NInput
                id="prompt"
                v-model:value="customInstructions"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 5 }"
                maxlength="2000"
                show-count
                :disabled="isRunning"
                placeholder="例如：重点关注 RAG 评测与工作流落地经验"
              />
              <div class="run-bar">
                <div>
                  <strong>{{ readyResumes.length }} 份</strong>
                  <span>简历将参与本次评估</span>
                </div>
                <NButton
                  v-if="!isRunning"
                  type="primary"
                  size="large"
                  :loading="submitting"
                  :disabled="
                    !readyResumes.length ||
                    jobDescription.trim().length < 20 ||
                    !privacyAccepted ||
                    !quotaAllowsBatch
                  "
                  @click="startEvaluation"
                >
                  <template #icon><NIcon :component="PlayerPlay" /></template>
                  开始批量评估
                </NButton>
                <NButton v-else type="error" ghost size="large" @click="stopEvaluation">
                  <template #icon><NIcon :component="PlayerStop" /></template>
                  停止任务
                </NButton>
              </div>
              <NCheckbox v-model:checked="privacyAccepted" class="privacy-check" :disabled="isRunning">
                我确认有权处理这些简历，并同意将提取文本发送至本站、Dify 和模型服务商。
              </NCheckbox>
              <NAlert
                v-if="readyResumes.length && !quotaAllowsBatch"
                type="warning"
                :show-icon="false"
                class="action-alert"
              >
                当前额度不足：本 IP 今日剩余 {{ quota?.per_ip_remaining ?? 0 }} 份，
                全站剩余 {{ quota?.global_remaining ?? 0 }} 份。请减少文件数量或明日再试。
              </NAlert>
              <NAlert v-if="actionError" type="error" :show-icon="false" class="action-alert">
                {{ actionError }}
              </NAlert>
              <div v-if="task" class="progress-card">
                <div class="progress-copy">
                  <strong>{{ isRunning ? "正在评估候选人" : task.status === "cancelled" ? "任务已取消" : "本次评估已完成" }}</strong>
                  <span>
                    成功 {{ task.summary.success }} · 失败 {{ task.summary.failed }} ·
                    进行中 {{ task.summary.running }}
                  </span>
                </div>
                <NProgress
                  type="line"
                  :percentage="progress"
                  :status="task.summary.failed ? 'warning' : 'success'"
                  :processing="isRunning"
                />
              </div>
            </section>
          </div>

          <ResultTable
            :items="task?.items || []"
            :task-id="task?.task_id || null"
            @delete="removeTask"
          />
        </main>

        <footer>
          <span>AI 只负责整理证据与提示风险，最终判断始终由招聘人员完成。</span>
          <span>受限演示版 · 结果最多保留 2 小时</span>
        </footer>
      </div>
    </NMessageProvider>
  </NConfigProvider>
</template>
