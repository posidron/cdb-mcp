/*
 * samples/very-hard/pipeline.cpp
 *
 * An event processing pipeline: ingests log events, indexes them
 * by ID for fast lookup, and produces formatted summaries.
 * Realistic enterprise-grade code with no suspicious names or strings.
 *
 * Build (MSVC, debug, x64):
 *   cl /Zi /Od /EHsc /Fe:pipeline.exe pipeline.cpp
 *
 * Usage:
 *   pipeline.exe
 *
 * =====================================================================
 * ANSWER KEY — contains 3 bugs (do NOT read before debugging):
 *
 *   Bug 1: USE-AFTER-REALLOC VIA CACHED POINTER
 *     In run_pipeline(), a pointer to entries[0] is cached before
 *     subsequent store_append() calls trigger grow_store(). The
 *     grow_store() function uses realloc() which may relocate the
 *     backing buffer to a new address. The cached pointer becomes
 *     dangling. A subsequent write through it modifies freed heap
 *     memory — a use-after-free that silently corrupts the heap.
 *     The corruption is visible by comparing cached->severity with
 *     store->entries[0].severity after the write (they differ).
 *
 *   Bug 2: SIGNED INTEGER OVERFLOW → NEGATIVE MODULO → OOB ACCESS
 *     compute_slot() multiplies event_id by 2999 using signed int32
 *     arithmetic. For event_id = 800000, the product 2,399,200,000
 *     exceeds INT_MAX (2,147,483,647) and wraps to -1,895,767,296.
 *     C's % operator preserves sign: -1895767296 % 31 = -23.
 *     This negative value is used as an array index into the lookup
 *     table's slots[], accessing 23 * sizeof(Slot) = 276 bytes
 *     BEFORE the array start. Since the table is on the stack, this
 *     silently corrupts adjacent local variables (no immediate crash).
 *
 *   Bug 3: sizeof(ptr) VS sizeof(*ptr) ALLOCATION MISMATCH
 *     In format_report(), the programmer wrote:
 *       EventRecord* buf = (EventRecord*)malloc(sizeof(buf));
 *     sizeof(buf) evaluates to sizeof(EventRecord*) = 8 bytes (x64).
 *     The intent was sizeof(*buf) = sizeof(EventRecord) = 80 bytes.
 *     The subsequent memcpy writes 80 bytes into an 8-byte heap
 *     allocation, overflowing by 72 bytes. This corrupts heap
 *     metadata and triggers a heap integrity check failure.
 * =====================================================================
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>

/* ---- data structures --------------------------------------------------- */

struct EventRecord {
    int       id;
    int       severity;
    long long timestamp;
    char      tag[64];
};

struct Store {
    EventRecord* entries;
    int          count;
    int          capacity;
};

#define TABLE_SIZE 31

struct Slot {
    int used;
    int key;
    int value;
};

struct LookupTable {
    Slot entries[TABLE_SIZE];
};

/* ---- storage ----------------------------------------------------------- */

static Store* init_store(int cap) {
    Store* s = (Store*)malloc(sizeof(Store));
    s->entries = (EventRecord*)malloc(cap * sizeof(EventRecord));
    s->count = 0;
    s->capacity = cap;
    return s;
}

static void grow_store(Store* s) {
    s->capacity *= 2;
    s->entries = (EventRecord*)realloc(s->entries,
                                        s->capacity * sizeof(EventRecord));
}

static int store_append(Store* s, int id, int sev, long long ts,
                        const char* tag) {
    if (s->count >= s->capacity)
        grow_store(s);
    EventRecord* r = &s->entries[s->count];
    r->id = id;
    r->severity = sev;
    r->timestamp = ts;
    memset(r->tag, 0, sizeof(r->tag));
    int len = (int)strlen(tag);
    if (len > (int)sizeof(r->tag) - 1)
        len = (int)sizeof(r->tag) - 1;
    memcpy(r->tag, tag, len);
    return s->count++;
}

/* ---- lookup table ------------------------------------------------------ */

static int compute_slot(int key) {
    int h = key * 2999;
    return h % TABLE_SIZE;
}

static void table_insert(LookupTable* t, int key, int value) {
    int slot = compute_slot(key);
    while (t->entries[slot].used) {
        slot = (slot + 1) % TABLE_SIZE;
    }
    t->entries[slot].used = 1;
    t->entries[slot].key = key;
    t->entries[slot].value = value;
}

static int table_find(LookupTable* t, int key) {
    int slot = compute_slot(key);
    for (int i = 0; i < TABLE_SIZE; i++) {
        if (!t->entries[slot].used)
            return -1;
        if (t->entries[slot].key == key)
            return t->entries[slot].value;
        slot = (slot + 1) % TABLE_SIZE;
    }
    return -1;
}

/* ---- reporting --------------------------------------------------------- */

static void format_report(Store* s, LookupTable* t, int target_id) {
    int pos = table_find(t, target_id);
    if (pos < 0) {
        printf("  [report] event %d: not found\n", target_id);
        return;
    }

    EventRecord* buf = (EventRecord*)malloc(sizeof(buf));
    memcpy(buf, &s->entries[pos], sizeof(EventRecord));

    printf("  [report] id=%d sev=%d tag=%.32s\n",
           buf->id, buf->severity, buf->tag);
    free(buf);
}

/* ---- pipeline ---------------------------------------------------------- */

static void run_pipeline() {
    printf("== Event Processing Pipeline ==\n");

    Store* store = init_store(2);
    LookupTable table;
    memset(&table, 0, sizeof(table));

    /* Phase 1: Ingest */
    printf("[phase 1] ingesting events\n");

    store_append(store, 101, 3, 1709000001LL, "boot sequence");
    store_append(store, 102, 2, 1709000002LL, "config loaded");

    EventRecord* cached = &store->entries[0];
    printf("  cached ptr at %p (id=%d)\n", (void*)cached, cached->id);

    /* Fragment heap so realloc is forced to relocate */
    void* pad1 = malloc(4096);
    void* pad2 = malloc(4096);

    store_append(store, 103, 5, 1709000003LL, "threshold exceeded");
    store_append(store, 104, 1, 1709000004LL, "session opened");
    store_append(store, 105, 4, 1709000005LL, "resource pressure");

    free(pad1);
    free(pad2);

    /* Phase 2: Update cached record — stale pointer */
    printf("[phase 2] updating cached event\n");
    cached->severity = 99;
    printf("  via cached ptr: severity=%d\n", cached->severity);
    printf("  via store[0]:   severity=%d\n", store->entries[0].severity);

    /* Phase 3: Index */
    printf("[phase 3] building index\n");
    for (int i = 0; i < store->count; i++) {
        table_insert(&table, store->entries[i].id, i);
    }

    printf("[phase 4] indexing additional record\n");
    int pos = store_append(store, 800000, 3, 1709999999LL, "periodic check");
    table_insert(&table, 800000, pos);

    /* Phase 5: Report */
    printf("[phase 5] generating report\n");
    format_report(store, &table, 103);

    /* Cleanup */
    free(store->entries);
    free(store);
    printf("== Pipeline Complete ==\n");
}

int main() {
    run_pipeline();
    return 0;
}
