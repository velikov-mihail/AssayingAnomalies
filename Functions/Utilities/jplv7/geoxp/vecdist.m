function distmat = vecdist(mat1, mat2)
% VECDIST Distance between two set of vectors
%	VECDIST(MAT1, MAT2) returns the distance matrix between two
%	set of vectors MAT1 and MAT2. The element at row i and column j
%	of the return matrix is the Euclidean distance between row i
%	of MAT1 and row j of MAT2.

%	Roger Jang, Sept 24, 1996.

if nargin == 1,
	mat2 = mat1;
end

[m1, n1] = size(mat1);
[m2, n2] = size(mat2);

if n1 ~= n2,
	error('Matrices mismatch!');
end

distmat = zeros(m1, m2);

if n1 == 1,
	distmat = abs(mat1*ones(1,m2)-ones(m1,1)*mat2');
elseif m2 >= m1,
	for i = 1:m1,
		distmat(i,:) = sqrt(sum(((ones(m2,1)*mat1(i,:)-mat2)').^2));
	end
else 
	for i = 1:m2,
		distmat(:,i) = sqrt(sum(((mat1-ones(m1,1)*mat2(i,:))').^2))';
	end
end
