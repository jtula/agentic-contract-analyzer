---
name: q-issue-generator
description: This skill generates detailed, structured GitHub issue descriptions from brief ideas or requirements. It automatically classifies the input as a system use case, infrastructure/internal task, or bug report and produces Spanish-language issue descriptions.
---

# Q-Issue Generator

## Purpose

Transform brief ideas, requirements, or bug reports into comprehensive, structured GitHub issue descriptions. Automatically classify whether the input is a system use case (user-facing functionality) or an infrastructure/internal task (team-facing work). All output is in Spanish and formatted for GitHub.

## When to Use

Use this skill when:
- The user provides a brief idea and asks to generate an issue/use case
- Converting a rough requirement into structured documentation
- Creating GitHub issues from informal descriptions
- Documenting use cases from user stories or feature requests
- Writing bug reports with proper reproduction steps
- Planning infrastructure or internal team tasks

## Classification Logic

### System Use Case (Caso de Uso del Sistema)

An input is a **system use case** when:
- Involves an external actor (user, client, external system) interacting with the system
- Describes functionality visible from outside the system
- Has a clear user goal and observable outcome
- Examples: "Usuario se registra", "Cliente consulta saldo", "Sistema envía notificación"

**Use template:** `references/templates.md` → "Caso de Uso del Sistema"

### Infrastructure/Internal Task (Tarea de Infraestructura/Interna)

An input is an **infrastructure/internal task** when:
- Involves internal systems, DevOps, tooling, or team processes
- No direct external actor interacts with the functionality
- Describes technical improvements, refactors, setup, or maintenance
- Examples: "Configurar CI/CD", "Migrar base de datos", "Actualizar dependencias", "Crear documentación"

**Use template:** `references/templates.md` → "Tarea de Infraestructura/Interna"

### Bug (Error)

An input is a **bug** when:
- Describes something that is broken or not working as expected
- Has steps to reproduce and expected vs actual behavior

**Use template:** `references/templates.md` → "Bug Report"

## How to Use

### 1. Classify the Input

Analyze the input and determine its type using the classification logic above. If unsure, ask the user:
- "¿Este flujo involucra un usuario externo o es trabajo interno del equipo?"
- "¿Es una funcionalidad que un usuario final va a usar?"

### 2. Ask Clarifying Questions

If the idea is too vague, ask targeted questions:
- **Use Case**: "¿Quién es el actor principal?", "¿Qué objetivo tiene?", "¿Hay flujos alternativos?"
- **Infra/Internal**: "¿Qué sistema/componente afecta?", "¿Hay deadline o milestone?", "¿Quién debería asignarse?"

### 3. Generate the Issue File

**Critical:** The output MUST be saved as a `.md` file in the `issues/` directory at the root of the project.

**File naming convention:**
- Format: `issues/{NNNN}-{type}-{slug}.md`
- `{NNNN}`: 4-digit sequential number starting at `0001`
- `{type}`: `uc` (use case), `infra` (infrastructure), `bug` (bug report)
- `{slug}`: kebab-case summary of the title (max 4-5 words)

**Examples:**
- "Usuario inicia sesión" → `issues/0001-uc-usuario-inicia-sesion.md`
- "Configurar CI/CD" → `issues/0002-infra-configurar-ci-cd.md`
- "Error en registro" → `issues/0003-bug-error-en-registro.md`

**Process:**
1. Verify `issues/` directory exists; create it if not
2. Scan existing files to determine the next sequential number
   - If `issues/` is empty, start at `0001`
   - If files exist, find the highest number and increment by 1
   - Extract number from filename pattern `{NNNN}-*.md`
3. Generate the content using appropriate template from `references/templates.md`
4. write_to_file the file to `issues/{NNNN}-{type}-{slug}.md`
5. Report the created file path to the user

### 4. Issue Content

Use the appropriate template from `references/templates.md` and follow best practices from `references/best-practices.md`.

All issues must include GitHub-compatible metadata at the end:
- Labels sugeridas
- Milestone (si aplica)
- Assignees sugeridos (si se conoce)

## Output

- **File location:** `issues/` directory at project root
- **Format:** Markdown (`.md`)
- **Language:** Spanish

## Files

- `references/templates.md` - Templates for use cases, bugs, and infrastructure tasks (GitHub-compatible)
- `references/best-practices.md` - Writing guidelines and tips
- `references/examples.md` - Reference examples of well-written descriptions

## Output Directory Structure

```
issues/
├── 0001-uc-usuario-inicia-sesion.md
├── 0002-uc-cliente-consulta-pedidos.md
├── 0003-infra-configurar-ci-cd.md
├── 0004-infra-migrar-base-datos.md
├── 0005-bug-error-descuento-carrito.md
└── ...
```

## Example: Creating a Use Case Issue

**User input:** "quiero que los usuarios puedan subir documentos PDF al sistema"

1. **Classify**: This is a System Use Case (external user uploads documents)
2. **Generate**: Create `issues/XXXX-uc-subir-documentos-pdf.md`
3. **Content** (Spanish):

```markdown
# Caso de Uso: Subir Documentos PDF

## Resumen
El usuario puede subir documentos PDF al sistema para su procesamiento.

## Actor Principal
- Usuario externo

## Precondiciones
- Usuario autenticado en el sistema
- Cuenta activa

## Flujo Principal
1. Usuario accede a la página de carga de documentos
2. Sistema muestra formulario de carga
3. Usuario selecciona archivo PDF
4. Sistema valida formato y tamaño
5. Sistema procesa documento
6. Sistema confirma carga exitosa

## Poscondiciones
- Documento almacenado en el sistema
- Usuario recibe confirmación

## Labels Sugeridas
- `feature`
- `documents`
- `upload`

## Milestone
[Si aplica]
```

## Example: Creating an Infrastructure Issue

**User input:** "necesitamos migrar la base de datos a PostgreSQL"

1. **Classify**: This is an Infrastructure task (no external user)
2. **Generate**: `issues/XXXX-infra-migrar-postgres.md`
3. **Content** (Spanish):

```markdown
# Tarea: Migrar Base de Datos a PostgreSQL

## Resumen
Migrar la base de datos actual a PostgreSQL para mejorar rendimiento y escalabilidad.

## Contexto
- Sistema actual usa SQLite
- Necesitamos PostgreSQL para producción

## Tareas Técnicas
1. [ ] Configurar instancia PostgreSQL
2. [ ] Crear scripts de migración
3. [ ] Migrar datos existentes
4. [ ] Actualizar configuración de aplicación
5. [ ] Verificar funcionamiento

## Labels Sugeridas
- `infrastructure`
- `database`
- `migration`
```
