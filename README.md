FSND P4: Conference Central
=====



### Task 3: Handling multiple inequality queries of different properties

NDB currently restricts multiple inequality queries across different properties. This means it is impossible to use a single query to find Sessions which start before 7pm (< inequality), and are not workshops (!= inequality). My solution in this project is implemented as the `doubleInequalityFilter()` endpoint method which makes two separate inequality queries for 'non workshop sessions' and sessions which occur before 7pm, respectively. Subsequently, the common items between these two queries are then extracted using the _getMatchingItemsInList(list1, list2) function. The result is a list of sessions which are both 'non workshops' which occurs before 7pm.

