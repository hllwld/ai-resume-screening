<script setup lang="ts">
import { computed, h, ref } from "vue";
import {
  NButton,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NIcon,
  NInput,
  NSelect,
  NStatistic,
  NTag,
  type DataTableColumns,
} from "naive-ui";
import { Download, Search, TableExport, Eye, Trash } from "@vicons/tabler";
import type { BatchItem, EvaluationResult } from "../types";

const props = defineProps<{ items: BatchItem[]; taskId: string | null }>();
const emit = defineEmits<{ delete: [] }>();
const search = ref("");
const recommendation = ref<string | null>(null);
const active = ref<BatchItem | null>(null);
const hasResults = computed(() => props.items.some((item) => item.result));

const labels: Record<string, string> = {
  interview: "建议面试",
  manual_review: "人工复核",
  supplement: "补充材料",
  reject: "人工确认不推进",
};
const tagTypes: Record<string, "success" | "info" | "warning" | "error"> = {
  interview: "success",
  manual_review: "info",
  supplement: "warning",
  reject: "error",
};

const filtered = computed(() =>
  props.items.filter((item) => {
    const matchesSearch =
      !search.value ||
      item.file_name.toLowerCase().includes(search.value.toLowerCase()) ||
      item.result?.candidate_name.toLowerCase().includes(search.value.toLowerCase());
    const matchesRecommendation =
      !recommendation.value || item.result?.recommendation === recommendation.value;
    return matchesSearch && matchesRecommendation;
  }),
);

function scoreCell(value: number) {
  const className = value >= 80 ? "score high" : value >= 60 ? "score medium" : "score low";
  return h("span", { class: className }, value);
}

const columns: DataTableColumns<BatchItem> = [
  {
    title: "文件",
    key: "file_name",
    minWidth: 210,
    render: (row) =>
      h("div", { class: "table-file" }, [
        h("strong", row.file_name),
        row.error ? h("small", { title: row.error }, row.error) : null,
      ]),
  },
  {
    title: "候选人",
    key: "candidate",
    minWidth: 120,
    render: (row) => row.result?.candidate_name || "—",
  },
  {
    title: "总分",
    key: "score",
    width: 86,
    sorter: (a, b) => (a.result?.match_score || 0) - (b.result?.match_score || 0),
    render: (row) => (row.result ? scoreCell(row.result.match_score) : "—"),
  },
  {
    title: "建议",
    key: "recommendation",
    width: 138,
    render: (row) =>
      row.result
        ? h(
            NTag,
            { type: tagTypes[row.result.recommendation], round: true, size: "small" },
            { default: () => labels[row.result!.recommendation] },
          )
        : "—",
  },
  {
    title: "技能",
    key: "skill",
    width: 82,
    render: (row) => row.result?.dimension_scores.skill_match ?? "—",
  },
  {
    title: "经验",
    key: "experience",
    width: 82,
    render: (row) => row.result?.dimension_scores.experience_relevance ?? "—",
  },
  {
    title: "项目",
    key: "project",
    width: 82,
    render: (row) => row.result?.dimension_scores.project_relevance ?? "—",
  },
  {
    title: "状态",
    key: "status",
    width: 110,
    render: (row) =>
      h(
        NTag,
        {
          type:
            row.status === "success"
              ? "success"
              : row.status === "failed"
                ? "error"
                : row.status === "running"
                  ? "info"
                  : "default",
          size: "small",
          round: true,
        },
        { default: () => ({ pending: "等待中", running: "评估中", success: "完成", failed: "失败", cancelled: "已取消" })[row.status] },
      ),
  },
  {
    title: "",
    key: "actions",
    width: 72,
    fixed: "right",
    render: (row) =>
      h(
        NButton,
        { quaternary: true, circle: true, disabled: !row.result, onClick: () => (active.value = row) },
        { icon: () => h(NIcon, { component: Eye }) },
      ),
  },
];

function csvEscape(value: unknown): string {
  const text = Array.isArray(value) ? value.join("；") : String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

function downloadCsv() {
  const headers = ["文件名", "候选人", "综合匹配分", "建议", "技能匹配", "相关经验", "项目相关性", "综合质量", "匹配技能", "待补充信息", "风险标记"];
  const rows = props.items
    .filter((item) => item.result)
    .map((item) => {
      const result = item.result!;
      return [
        item.file_name,
        result.candidate_name,
        result.match_score,
        result.recommendation,
        result.dimension_scores.skill_match,
        result.dimension_scores.experience_relevance,
        result.dimension_scores.project_relevance,
        result.dimension_scores.overall_quality,
        result.matched_skills,
        result.missing_information,
        result.risk_flags,
      ].map(csvEscape).join(",");
    });
  const blob = new Blob(["\ufeff", headers.map(csvEscape).join(","), "\n", rows.join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "candidate-review.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function listBlock(title: string, values: string[]) {
  return { title, values };
}

const detailBlocks = computed(() => {
  const result = active.value?.result;
  if (!result) return [];
  return [
    listBlock("匹配技能", result.matched_skills),
    listBlock("待补充信息", result.missing_information),
    listBlock("风险标记", result.risk_flags),
    listBlock("建议面试问题", result.recommended_interview_questions),
  ];
});
</script>

<template>
  <section class="results-section">
    <div class="results-heading">
      <div>
        <span class="eyebrow">03 / 评估结果</span>
        <h2>候选人评估清单</h2>
      </div>
      <div class="result-actions">
        <NButton :disabled="!items.some((item) => item.result)" @click="downloadCsv">
          <template #icon><NIcon :component="Download" /></template>
          CSV
        </NButton>
        <NButton
          v-if="taskId && hasResults"
          type="primary"
          tag="a"
          :href="`/api/batches/${taskId}/export.xlsx`"
        >
          <template #icon><NIcon :component="TableExport" /></template>
          下载复核 Excel
        </NButton>
        <NButton v-else type="primary" disabled>
          <template #icon><NIcon :component="TableExport" /></template>
          下载复核 Excel
        </NButton>
        <NButton
          v-if="taskId"
          type="error"
          ghost
          :disabled="items.some((item) => item.status === 'running')"
          @click="emit('delete')"
        >
          <template #icon><NIcon :component="Trash" /></template>
          删除结果
        </NButton>
      </div>
    </div>

    <div class="result-toolbar">
      <NInput v-model:value="search" clearable placeholder="搜索文件名或候选人">
        <template #prefix><NIcon :component="Search" /></template>
      </NInput>
      <NSelect
        v-model:value="recommendation"
        clearable
        placeholder="全部建议"
        :options="[
          { label: '建议面试', value: 'interview' },
          { label: '人工复核', value: 'manual_review' },
          { label: '补充材料', value: 'supplement' },
          { label: '人工确认不推进', value: 'reject' },
        ]"
      />
      <span class="result-count">共 {{ filtered.length }} 条</span>
    </div>

    <NDataTable
      v-if="items.length"
      :columns="columns"
      :data="filtered"
      :row-key="(row: BatchItem) => row.item_id"
      :pagination="{ pageSize: 10 }"
      :scroll-x="1100"
      striped
    />
    <NEmpty v-else description="完成文件解析并开始评估后，结果会显示在这里" class="result-empty" />

    <NDrawer
      :show="Boolean(active)"
      :width="560"
      @update:show="(show) => { if (!show) active = null }"
    >
      <NDrawerContent v-if="active?.result" :title="active.result.candidate_name" closable>
        <div class="drawer-score">
          <NStatistic label="综合匹配分" :value="active.result.match_score" />
          <NTag :type="tagTypes[active.result.recommendation]" round>
            {{ labels[active.result.recommendation] }}
          </NTag>
        </div>
        <div class="dimension-grid">
          <div><span>技能匹配</span><strong>{{ active.result.dimension_scores.skill_match }}</strong></div>
          <div><span>相关经验</span><strong>{{ active.result.dimension_scores.experience_relevance }}</strong></div>
          <div><span>项目相关性</span><strong>{{ active.result.dimension_scores.project_relevance }}</strong></div>
          <div><span>综合质量</span><strong>{{ active.result.dimension_scores.overall_quality }}</strong></div>
        </div>
        <div v-for="block in detailBlocks" :key="block.title" class="detail-block">
          <h3>{{ block.title }}</h3>
          <ul v-if="block.values.length">
            <li v-for="value in block.values" :key="value">{{ value }}</li>
          </ul>
          <p v-else class="muted">无</p>
        </div>
        <div class="detail-block">
          <h3>评分证据</h3>
          <div v-for="(values, key) in active.result.evidence" :key="key" class="evidence-row">
            <span>{{ { skill_match: "技能", experience_relevance: "经验", project_relevance: "项目", overall_quality: "质量" }[key] }}</span>
            <p>{{ values.length ? values.join("；") : "无直接证据" }}</p>
          </div>
        </div>
        <p class="review-note">{{ active.result.human_review_note }}</p>
      </NDrawerContent>
    </NDrawer>
  </section>
</template>
