<script setup lang="ts">
import { computed, ref } from "vue";
import {
  NButton,
  NEmpty,
  NIcon,
  NProgress,
  NTag,
  NTooltip,
  useMessage,
} from "naive-ui";
import {
  Folder,
  FileUpload,
  Trash,
  FileText,
  AlertTriangle,
} from "@vicons/tabler";
import { parsePdf } from "../pdf";
import type { ParsedResume } from "../types";

const props = defineProps<{ files: ParsedResume[]; disabled: boolean }>();
const emit = defineEmits<{ "update:files": [value: ParsedResume[]] }>();
const message = useMessage();
const folderInput = ref<HTMLInputElement>();
const filesInput = ref<HTMLInputElement>();
const parsing = ref(false);

const readyCount = computed(() => props.files.filter((f) => f.state === "ready").length);

async function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  const selected = Array.from(input.files || [])
    .filter((file) => file.name.toLowerCase().endsWith(".pdf"))
    .slice(0, Math.max(0, 10 - props.files.length));
  input.value = "";
  if (!selected.length) {
    message.warning("没有找到可读取的 PDF");
    return;
  }
  parsing.value = true;
  const existingFiles = [...props.files];
  const placeholders = selected.map((file) => ({
    id: crypto.randomUUID(),
    fileName: file.name,
    relativePath: file.webkitRelativePath || file.name,
    size: file.size,
    pages: 0,
    chars: 0,
    text: "",
    state: "parsing" as const,
  }));
  emit("update:files", [...existingFiles, ...placeholders]);

  const results: ParsedResume[] = [];
  for (const file of selected) {
    results.push(await parsePdf(file));
    emit("update:files", [
      ...existingFiles,
      ...results,
      ...placeholders.slice(results.length),
    ]);
  }
  parsing.value = false;
  message.success(`读取完成：${results.filter((item) => item.state === "ready").length} 份可评估`);
}

function removeFile(id: string) {
  emit("update:files", props.files.filter((file) => file.id !== id));
}
</script>

<template>
  <section class="panel file-panel">
    <div class="panel-heading">
      <div>
        <span class="eyebrow">01 / 简历文件</span>
        <h2>选择要评估的 PDF</h2>
        <p>文件只在浏览器中解析，提取后的文字会发送到 Dify。</p>
      </div>
      <div class="heading-count">
        <strong>{{ readyCount }}</strong>
        <span>可评估</span>
      </div>
    </div>

    <div class="picker-actions">
      <input
        ref="folderInput"
        class="visually-hidden"
        type="file"
        accept=".pdf,application/pdf"
        multiple
        webkitdirectory
        @change="selectFiles"
      />
      <input
        ref="filesInput"
        class="visually-hidden"
        type="file"
        accept=".pdf,application/pdf"
        multiple
        @change="selectFiles"
      />
      <NButton type="primary" size="large" :disabled="disabled || parsing" @click="folderInput?.click()">
        <template #icon><NIcon :component="Folder" /></template>
        选择文件夹
      </NButton>
      <NButton size="large" :disabled="disabled || parsing" @click="filesInput?.click()">
        <template #icon><NIcon :component="FileUpload" /></template>
        选择多个 PDF
      </NButton>
      <span class="limit-note">最多 10 份 · 单份 10 MB / 30 页 / 6 万字符</span>
    </div>

    <NProgress v-if="parsing" type="line" :percentage="100" processing :show-indicator="false" />

    <div v-if="files.length" class="file-list">
      <article v-for="file in files" :key="file.id" class="file-row">
        <div class="file-icon" :class="file.state">
          <NIcon :component="file.state === 'scan' || file.state === 'error' ? AlertTriangle : FileText" />
        </div>
        <div class="file-copy">
          <strong :title="file.relativePath">{{ file.fileName }}</strong>
          <span v-if="file.state === 'parsing'">正在提取文字…</span>
          <span v-else-if="file.error">{{ file.error }}</span>
          <span v-else>{{ file.pages }} 页 · {{ file.chars.toLocaleString() }} 字符</span>
        </div>
        <NTag
          size="small"
          round
          :type="file.state === 'ready' ? 'success' : file.state === 'parsing' ? 'info' : 'warning'"
        >
          {{ { ready: "可评估", parsing: "读取中", scan: "需 OCR", error: "不可用" }[file.state] }}
        </NTag>
        <NTooltip>
          <template #trigger>
            <NButton quaternary circle :disabled="disabled" @click="removeFile(file.id)">
              <template #icon><NIcon :component="Trash" /></template>
            </NButton>
          </template>
          移除
        </NTooltip>
      </article>
    </div>
    <NEmpty v-else description="尚未选择简历文件" class="empty-files" />
  </section>
</template>
