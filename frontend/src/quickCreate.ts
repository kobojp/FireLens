import type { TreeNode } from './types'

export type QuickCreateSelection = {
  category_code: string
  year: string
  period: string
  building: string
}

export type QuickCreateOptions = {
  years: string[]
  periods: string[]
  buildings: string[]
}

function childrenOf(node: TreeNode | undefined, type: TreeNode['type']): TreeNode[] {
  return (node?.children ?? []).filter((child) => child.type === type)
}

function sameValue(node: TreeNode, value: string): boolean {
  const target = value.trim()
  return node.key.trim() === target || node.label.trim() === target
}

function findChild(node: TreeNode | undefined, type: TreeNode['type'], key: string): TreeNode | undefined {
  return childrenOf(node, type).find((child) => sameValue(child, key))
}

function categoryNode(nodes: TreeNode[], code: string): TreeNode | undefined {
  return nodes.find((node) => node.type === 'category' && sameValue(node, code))
}

function orderedLabels(nodes: TreeNode[]): string[] {
  return nodes.map((node) => node.label)
}

function chooseYear(options: string[], current: string, now: Date): string {
  if (options.includes(current)) return current
  const calendarYear = `${now.getFullYear()}年`
  if (options.includes(calendarYear)) return calendarYear
  return options.at(-1) ?? (current || calendarYear)
}

function choosePeriod(options: string[], current: string, now: Date): string {
  if (options.includes(current)) return current
  const monthPrefix = `${now.getMonth() + 1}月份`
  const calendarMonth = options.find((option) => option.startsWith(monthPrefix))
  if (calendarMonth) return calendarMonth
  return options.at(-1) ?? current
}

export function quickCreateOptions(
  nodes: TreeNode[],
  selection: QuickCreateSelection,
  now = new Date(),
): QuickCreateOptions {
  const category = categoryNode(nodes, selection.category_code)
  const years = orderedLabels(childrenOf(category, 'year'))
  const effectiveYear = chooseYear(years, selection.year.trim(), now)
  const year = findChild(category, 'year', effectiveYear)
  const periods = orderedLabels(childrenOf(year, 'period'))
  const effectivePeriod = choosePeriod(periods, selection.period.trim(), now)
  const period = findChild(year, 'period', effectivePeriod)
  const buildings = orderedLabels(childrenOf(period, 'building'))
  return { years, periods, buildings }
}

export function normalizeQuickCreate(
  nodes: TreeNode[],
  selection: QuickCreateSelection,
  now = new Date(),
): QuickCreateSelection {
  const category = categoryNode(nodes, selection.category_code.trim())
  const years = orderedLabels(childrenOf(category, 'year'))
  const year = chooseYear(years, selection.year.trim(), now)
  const yearNode = findChild(category, 'year', year)
  const periods = orderedLabels(childrenOf(yearNode, 'period'))
  const period = choosePeriod(periods, selection.period.trim(), now)
  const periodNode = findChild(yearNode, 'period', period)
  const buildings = orderedLabels(childrenOf(periodNode, 'building'))
  const savedBuilding = selection.building.trim()
  const building = buildings.includes(savedBuilding)
    ? savedBuilding
    : buildings[0] ?? savedBuilding
  return { ...selection, category_code: selection.category_code.trim(), year, period, building }
}
