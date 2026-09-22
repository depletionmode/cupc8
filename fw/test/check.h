/* Minimal test harness for the firmware cores' host tests. */
#ifndef CHECK_H
#define CHECK_H

#include <stdio.h>
#include <stdlib.h>

static int check_failures, check_count;

#define CHECK(cond, ...) do {                                              \
	check_count++;                                                         \
	if (!(cond)) {                                                         \
		check_failures++;                                                  \
		fprintf(stderr, "%s:%d: FAIL %s: ", __FILE__, __LINE__, #cond);    \
		fprintf(stderr, __VA_ARGS__);                                      \
		fprintf(stderr, "\n");                                             \
	}                                                                      \
} while (0)

#define CHECK_EQ(a, b) CHECK((long)(a) == (long)(b), "%ld != %ld", (long)(a), (long)(b))

static inline int check_report(const char *name)
{
	printf("%s: %d checks, %d failures\n", name, check_count, check_failures);
	return check_failures ? 1 : 0;
}

#endif
